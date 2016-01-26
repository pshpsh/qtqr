#!/usr/bin/env python

# Authors:
#   David Green <david4dev@gmail.com>
#   Ramiro Algozino <algozino@gmail.com>
#
# qrtools.py: Library for encoding/decoding QR Codes (2D barcodes).
# Copyright (C) 2011 David Green <david4dev@gmail.com>
#
# `qrtools.py` is free software: you can redistribute it and/or modify it under the
# terms of the GNU General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option) any
# later version.
#
# `qrtools.py` is distributed in the hope that it will be useful, but WITHOUT ANY
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR
# A PARTICULAR PURPOSE.  See the GNU General Public License for more
# details.
#
# You should have received a copy of the GNU General Public License along
# with `qrtools.py`.  If not, see <http://www.gnu.org/licenses/>.

import subprocess
import os
import time
import shutil
import hashlib
import zbar
try:
    from PIL import Image
except ImportError:
    import Image
import re
from codecs import BOM_UTF8

class QR(object):

    def encode_url(data):
        data_lower = data.lower()
        if data_lower.startswith(u"http://"):
            return ('http://' + re.compile(
                r'^http://', re.IGNORECASE
            ).sub('', data))
        elif data_lower.startswith(u"https://"):
            return ('https://' + re.compile(
                r'^https://', re.IGNORECASE
            ).sub('', data))

    #use these for custom data formats eg. url, phone number, VCARD
    #data should be an unicode object or a list of unicode objects
    data_encode = {
        'text' : lambda data: data,
        'url' : encode_url,
        'email' :lambda data: 'mailto:' + re.compile(
                r'^mailto:', re.IGNORECASE
            ).sub('', data),
        'emailmessage' : lambda data : 'MATMSG:TO:' + data[0] + ';SUB:' + data[1] + ';BODY:' + data[2] + ';;',
        'telephone' : lambda data: 'tel:' + re.compile(
                r'^tel:', re.IGNORECASE
            ).sub('', data),
        'sms' : lambda data : 'SMSTO:' + data[0] + ':' + data[1],
        'mms' : lambda data : 'MMSTO:' + data[0] + ':' + data[1],
        'geo' : lambda data : 'geo:' + data[0] + ',' + data[1],
        'bookmark': lambda data : "MEBKM:TITLE:" + data[0] + ";URL:" + data[1] + ";;",
        # phonebook or meCard should be a list of tuples like this:
        # [('N','Name'),('TEL', '231698890'), ...]
        'phonebook': lambda data: "MECARD:" + ";".join([":".join(i) for i in data]) + ";",
        'wifi': lambda data: "WIFI:S:" + data[0] + ";T:" + data[1] + ";P:" + data[2] +";;",
    }

    data_decode = {
        'text': lambda data: data,
        'url': lambda data: data,
        'email': lambda data: data.replace(u"mailto:",u"").replace(u"MAILTO:",u""),
        'emailmessage': lambda data: re.findall(u"MATMSG:TO:(.*);SUB:(.*);BODY:(.*);;", data, re.IGNORECASE)[0],
        'telephone': lambda data: data.replace(u"tel:",u"").replace(u"TEL:",u""),
        'sms': lambda data: re.findall(u"SMSTO:(.*):(.*)", data, re.IGNORECASE)[0],
        'mms': lambda data: re.findall(u"MMSTO:(.*):(.*)", data, re.IGNORECASE)[0],
        'geo': lambda data: re.findall(u"GEO:(.*),(.*)", data, re.IGNORECASE)[0],
        'bookmark': lambda data: re.findall(u"MEBKM:TITLE:(.*);URL:(.*);;", data, re.IGNORECASE)[0],
        'phonebook': lambda data: dict(re.findall("(.*?):(.*?);", data.replace("MECARD:",""), re.IGNORECASE)),
        'wifi' : lambda data: re.findall(u"WIFI:S:(.*);T:(.*);P:(.*);;", data, re.IGNORECASE)[0],
    }

    def data_recognise(self, data = None):
        """Returns an unicode string indicating the data type of the data paramater"""
        data = data or self.data 
        data_lower = data.lower()
        if data_lower.startswith(u"http://") or data_lower.startswith(u"https://"): return u'url'
        elif data_lower.startswith(u"mailto:"): return u'email'
        elif data_lower.startswith(u"matmsg:to:"): return u'emailmessage'
        elif data_lower.startswith(u"tel:"): return u'telephone'
        elif data_lower.startswith(u"smsto:"): return u'sms'
        elif data_lower.startswith(u"mmsto:"): return u'mms'
        elif data_lower.startswith(u"geo:"): return u'geo'
        elif data_lower.startswith(u"mebkm:title:"): return u'bookmark'
        elif data_lower.startswith(u"mecard:"): return u'phonebook'
        elif data_lower.startswith(u"wifi:"): return u'wifi'
        else: return u'text'

    def __init__(
        self, data=u'NULL', pixel_size=3, level='L', margin_size=4,
        data_type=u'text', filename=None
    ):
        self.pixel_size = pixel_size
        self.level = level
        self.margin_size = margin_size
        self.data_type = data_type
        #you should pass data as a unicode object or a list/tuple of unicode objects.
        self.data = data
        #get a temp directory
        self.directory = os.path.join('/tmp', 'qr-%f' % time.time())
        self.filename = filename
        os.makedirs(self.directory)
        self.qrencode_version = self.get_qrencode_version()
        self.qrencode_types = self.get_qrencode_types()

    def data_to_string(self):
        """Returns a UTF8 string with the QR Code's data"""
        # FIX-ME: if we don't add the BOM_UTF8 char, QtQR doesn't decode 
        # correctly; but if we add it, mobile apps don't.- 
        # /Apparently/ Confirmed that is a zbar bug.
        # See: https://bugs.launchpad.net/qr-tools/+bug/796387
        if self.data_type == 'text':
            return BOM_UTF8 + self.__class__.data_encode[self.data_type](self.data).encode('utf-8')
        else:
            return self.__class__.data_encode[self.data_type](self.data).encode('utf-8')

    def get_tmp_file(self):
        return os.path.join(
            self.directory,
            #filename is hash of data
            hashlib.sha256(self.data_to_string()).hexdigest() + '.png'
        )

    def encode(self, filename=None):
        self.filename = filename or self.get_tmp_file()
        ext = os.path.splitext(self.filename)[1].replace('.', '').upper()
        if  ext != 'PNG' \
        and ext != 'EPS' \
        and ext != 'SVG' \
        and ext != 'ANSI' \
        and ext != 'ANSI256' \
        and ext != 'ASCII' \
        and ext != 'ASCIII' \
        and ext != 'UTF8' \
        and ext != 'ANSIUTF8':
            self.filename += '.png'
            ext = 'PNG'
        if self.qrencode_version > '3.1.1':
            command = [
                'qrencode',
                '-o', self.filename,
                '-s', unicode(self.pixel_size),
                '-m', unicode(self.margin_size),
                '-l', self.level,
                '-t', ext,
                self.data_to_string()
            ]
        else:
            command = [
                'qrencode',
                '-o', self.filename,
                '-s', unicode(self.pixel_size),
                '-m', unicode(self.margin_size),
                '-l', self.level,
                #'-t', ext,
                self.data_to_string()
            ]
        return subprocess.Popen(command).wait()

    def decode(self, filename=None):
        self.filename = filename or self.filename
        if self.filename:
            scanner = zbar.ImageScanner()
            # configure the reader
            scanner.parse_config('enable')
            # obtain image data
            pil = Image.open(self.filename).convert('L')
            width, height = pil.size
            raw = pil.tostring()
            # wrap image data
            image = zbar.Image(width, height, 'Y800', raw)
            # scan the image for barcodes
            result = scanner.scan(image)
            # extract results
            if result == 0: 
                return False
            else:
                for symbol in image:
                    pass
                # clean up
                del(image)
                #Assuming data is encoded in utf8
                self.data = symbol.data.decode(u'utf-8')
                self.data_type = self.data_recognise()
                return True
        else:
            return False

    def decode_webcam(self, callback=lambda s:None, device='/dev/video0'):
        # create a Processor
        proc = zbar.Processor()

        # configure the Processor
        proc.parse_config('enable')

        # initialize the Processor
        proc.init(device)

        # setup a callback
        def my_handler(proc, image, closure):
            # extract results
            for symbol in image:
                if not symbol.count:
                    self.data = symbol.data
                    self.data_type = self.data_recognise()
                    callback(symbol.data)

        proc.set_data_handler(my_handler)

        # enable the preview window
        proc.visible = True

        # initiate scanning
        proc.active = True
        try:
            proc.user_wait()
        except zbar.WindowClosed:
            pass

    def destroy(self):
        shutil.rmtree(self.directory)

    def get_qrencode_version(self):
        #Somehow qerencode writes this to stderr instead of stdout :-/
        #FIXME: Probably a future bug in newer versions.
        p = subprocess.Popen(['qrencode','-V'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        version_text = p.communicate()[1]
        version = re.search('version\s([\d.]*)',version_text) 
        if version:
            version_number = version.group(1)
        else:
            version_number = -1
        #print "Using qrencode version:", version_number
        return version_number

    def get_qrencode_types(self):
        p = subprocess.Popen(['qrencode','-h'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        help_text = p.communicate()[1]
        types_text = re.search('-t {([\w,]*)}', help_text) 
        if types_text:
            types = types_text.group(1).split(',')
            #print "The following format types have been found!:", types
        else:
            types = ['png']
            #print "Help text for format types not found. Using:", types
        return types
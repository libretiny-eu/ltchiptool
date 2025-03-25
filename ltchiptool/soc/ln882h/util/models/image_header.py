#!/usr/bin/env python3
# -*- coding:utf-8 -*-
#
# Copyright 2021 Shanghai Lightning Semiconductor Technology Co., LTD

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# fmt: off
# isort:skip_file

import struct
import zlib
from .ln_tools import *

IMAGE_TYPE_ATTACHE      = 0
IMAGE_TYPE_ORIGINAL     = 1
IMAGE_TYPE_ORIGINAL_XZ  = 2
IMAGE_TYPE_DIFF         = 3
IMAGE_TYPE_DIFF_XZ      = 4
IMAGE_TYPE_INVALID      = 5

__IMAGE_TYPE_DICT = {
    IMAGE_TYPE_ATTACHE      : "attache",
    IMAGE_TYPE_ORIGINAL     : "original",
    IMAGE_TYPE_ORIGINAL_XZ  : "original_xz",
    IMAGE_TYPE_DIFF         : "diff",
    IMAGE_TYPE_DIFF_XZ      : "diff_xz",
    IMAGE_TYPE_INVALID      : "invalid"
}


def image_type_num2str(type_num):
    return __IMAGE_TYPE_DICT.get(type_num, __IMAGE_TYPE_DICT.get(IMAGE_TYPE_INVALID))


def image_type_str2num(type_str):
    for k, v in __IMAGE_TYPE_DICT.items():
        if v == type_str:
            return k
    return IMAGE_TYPE_INVALID


class ImageHeader:
    def __init__(self, buffer=bytearray(256)):
        self.image_type         = 0
        self.ver                = 0
        self.ver_diff           = 0
        self.img_size_orig      = 0
        self.img_size_orig_xz   = 0
        self.img_size_diff      = 0
        self.img_size_diff_xz   = 0
        self.img_crc32_orig     = 0
        self.img_crc32_orig_xz  = 0
        self.img_crc32_diff     = 0
        self.img_crc32_diff_xz  = 0
        self.header_crc32       = 0

        if len(buffer) < 0x100:
            raise ValueError("buffer MUST has 256 bytes at least!!!")

        self.header_buffer = bytearray(256)
        self.header_buffer[:] = buffer[0:256]

        image_header_struct = struct.unpack("<I2H8I212BI", self.header_buffer)
        self.image_type         = image_header_struct[0]
        self.ver                = image_header_struct[1]
        self.ver_diff           = image_header_struct[2]
        self.img_size_orig      = image_header_struct[3]
        self.img_size_orig_xz   = image_header_struct[4]
        self.img_size_diff      = image_header_struct[5]
        self.img_size_diff_xz   = image_header_struct[6]
        self.img_crc32_orig     = image_header_struct[7]
        self.img_crc32_orig_xz  = image_header_struct[8]
        self.img_crc32_diff     = image_header_struct[9]
        self.img_crc32_diff_xz  = image_header_struct[10]
        self.header_crc32       = image_header_struct[-1]

    def toBytes(self):
        self.header_buffer[0] = get_num_at_byte(self.image_type, 0)
        self.header_buffer[1] = get_num_at_byte(self.image_type, 1)
        self.header_buffer[2] = get_num_at_byte(self.image_type, 2)
        self.header_buffer[3] = get_num_at_byte(self.image_type, 3)

        self.header_buffer[4] = get_num_at_byte(self.ver, 1)
        self.header_buffer[5] = get_num_at_byte(self.ver, 0)

        self.header_buffer[6] = get_num_at_byte(self.ver_diff, 0)
        self.header_buffer[7] = get_num_at_byte(self.ver_diff, 1)

        self.header_buffer[8]  = get_num_at_byte(self.img_size_orig, 0)
        self.header_buffer[9]  = get_num_at_byte(self.img_size_orig, 1)
        self.header_buffer[10] = get_num_at_byte(self.img_size_orig, 2)
        self.header_buffer[11] = get_num_at_byte(self.img_size_orig, 3)

        self.header_buffer[12] = get_num_at_byte(self.img_size_orig_xz, 0)
        self.header_buffer[13] = get_num_at_byte(self.img_size_orig_xz, 1)
        self.header_buffer[14] = get_num_at_byte(self.img_size_orig_xz, 2)
        self.header_buffer[15] = get_num_at_byte(self.img_size_orig_xz, 3)

        self.header_buffer[16] = get_num_at_byte(self.img_size_diff, 0)
        self.header_buffer[17] = get_num_at_byte(self.img_size_diff, 1)
        self.header_buffer[18] = get_num_at_byte(self.img_size_diff, 2)
        self.header_buffer[19] = get_num_at_byte(self.img_size_diff, 3)

        self.header_buffer[20] = get_num_at_byte(self.img_size_diff_xz, 0)
        self.header_buffer[21] = get_num_at_byte(self.img_size_diff_xz, 1)
        self.header_buffer[22] = get_num_at_byte(self.img_size_diff_xz, 2)
        self.header_buffer[23] = get_num_at_byte(self.img_size_diff_xz, 3)

        self.header_buffer[24] = get_num_at_byte(self.img_crc32_orig, 0)
        self.header_buffer[25] = get_num_at_byte(self.img_crc32_orig, 1)
        self.header_buffer[26] = get_num_at_byte(self.img_crc32_orig, 2)
        self.header_buffer[27] = get_num_at_byte(self.img_crc32_orig, 3)

        self.header_buffer[28] = get_num_at_byte(self.img_crc32_orig_xz, 0)
        self.header_buffer[29] = get_num_at_byte(self.img_crc32_orig_xz, 1)
        self.header_buffer[30] = get_num_at_byte(self.img_crc32_orig_xz, 2)
        self.header_buffer[31] = get_num_at_byte(self.img_crc32_orig_xz, 3)

        self.header_buffer[32] = get_num_at_byte(self.img_crc32_diff, 0)
        self.header_buffer[33] = get_num_at_byte(self.img_crc32_diff, 1)
        self.header_buffer[34] = get_num_at_byte(self.img_crc32_diff, 2)
        self.header_buffer[35] = get_num_at_byte(self.img_crc32_diff, 3)

        self.header_buffer[36] = get_num_at_byte(self.img_crc32_diff_xz, 0)
        self.header_buffer[37] = get_num_at_byte(self.img_crc32_diff_xz, 1)
        self.header_buffer[38] = get_num_at_byte(self.img_crc32_diff_xz, 2)
        self.header_buffer[39] = get_num_at_byte(self.img_crc32_diff_xz, 3)

        self.reCalcCRC32()

        return self.header_buffer

    def reCalcCRC32(self):
        self.header_crc32 = zlib.crc32(self.header_buffer[0:(256-4)])
        self.header_buffer[252] = get_num_at_byte(self.header_crc32, 0)
        self.header_buffer[253] = get_num_at_byte(self.header_crc32, 1)
        self.header_buffer[254] = get_num_at_byte(self.header_crc32, 2)
        self.header_buffer[255] = get_num_at_byte(self.header_crc32, 3)

    def getVerMajor(self):
        """
        byte[4] -- major -- ver [index 1]
        byte[5] -- minor -- ver [index 0]
        """
        major = int(self.header_buffer[4])
        return major

    def setVerMajor(self, major):
        self.header_buffer[4] = major
        self.ver = (major << 8) | (self.header_buffer[5])

    def getVerMinor(self):
        minor = int(self.header_buffer[5])
        return minor

    def setVerMinor(self, minor):
        self.header_buffer[5] = minor
        self.ver = (self.header_buffer[4] << 8) | minor

    def __str__(self):
        output ="--------  APP image header  --------\n"\
                "       image_type: 0x{_it:08X}\n"      \
                "              ver: 0x{_v:04x}\n"       \
                "         ver_diff: 0x{_vd:04X}\n"      \
                "    img_size_orig: 0x{_iso:08X}\n"     \
                " img_size_orig_xz: 0x{_isox:08X}\n"    \
                "    img_size_diff: 0x{_isd:08X}\n"     \
                " img_size_diff_xz: 0x{_isdx:08X}\n"    \
                "   img_crc32_orig: 0x{_ico:08X}\n"     \
                "img_crc32_orig_xz: 0x{_icox:08X}\n"    \
                "   img_crc32_diff: 0x{_icd:08X}\n"     \
                "img_crc32_diff_xz: 0x{_icdx:08X}\n"    \
                "     header_crc32: 0x{_hc:08X}\n"      \
                "--------------------------------------"\
                .format(_it=self.image_type, _v=self.ver, _vd=self.ver_diff,
                        _iso=self.img_size_orig, _isox=self.img_size_orig_xz,
                        _isd=self.img_size_diff, _isdx=self.img_size_diff_xz,
                        _ico=self.img_crc32_orig, _icox=self.img_crc32_orig_xz,
                        _icd=self.img_crc32_diff, _icdx=self.img_crc32_diff_xz,
                        _hc=self.header_crc32)
        return output

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

import lzma
import sys
import os
import struct
import zlib
import shutil
import argparse
from .models.part_desc_info import *
from .models.image_header import *


class OTATOOL:
    def __init__(self):
        self.part_desc_info_list    = []
        self.image_header           = None
        self.app_content            = None
        self.output_filepath        = None
        self.__input_filepath       = None

    def readPartTab(self) -> bool:
        try:
            with open(self.input_filepath, "rb") as fInputObj:
                fInputObj.seek(PARTITION_TAB_OFFSET, os.SEEK_SET)
                ptable_buffer = fInputObj.read(PARTITION_TAB_SIZE)

                offset = 0
                while offset < PARTITION_TAB_SIZE:
                    part_desc_info_buffer = ptable_buffer[offset : (offset + PARTITION_DESC_INFO_SIZE)]
                    part_type, start_addr, part_size, part_crc32 = struct.unpack("<IIII", part_desc_info_buffer)
                    if part_type >= PART_TYPE_INVALID:
                        break
                    crc32_recalc = zlib.crc32(part_desc_info_buffer[0:(3*4)]) & 0xFFFFFFFF
                    if part_crc32 != crc32_recalc:
                        break
                    # print("type: {_pt:>12}, start_addr: 0x{_sa:08X}, part_size: 0x{_ps:08X}, part_crc32: 0x{_pc:08X}"
                    #     .format(_pt=part_type, _sa=start_addr, _ps=part_size, _pc=part_crc32))

                    part_desc_info_obj = PartDescInfo(part_type, start_addr, part_size, part_crc32)
                    self.part_desc_info_list.append(part_desc_info_obj)
                    offset += PARTITION_DESC_INFO_SIZE
        except Exception as err:
            print("Error: open file failed: {}".format(str(err)))
            return False
        if len(self.part_desc_info_list) >= 3:
            return True
        else:
            return False

    def readAPP(self):
        if len(self.part_desc_info_list) < 3:
            print("Please make sure that partition table has at least 3 items!!!")
            return False

        app_desc_info = None
        for desc_info in self.part_desc_info_list:
            if isinstance(desc_info, PartDescInfo):
                if desc_info.part_type == PART_TYPE_APP:
                    app_desc_info = desc_info
                    break

        if app_desc_info is None:
            print("Please make sure that APP partition is in the partition table!!!")
            return False

        try:
            with open(self.input_filepath, "rb") as fInputObj:
                fInputObj.seek(app_desc_info.start_addr, os.SEEK_SET)
                app_image_header_buffer = fInputObj.read(256)

                # image header
                self.image_header = ImageHeader(app_image_header_buffer)

                # app content
                if self.image_header.image_type == IMAGE_TYPE_ORIGINAL:
                    fInputObj.seek(app_desc_info.start_addr + 256, os.SEEK_SET)
                    self.app_content = fInputObj.read(self.image_header.img_size_orig)
                else:
                    print("Not supported image type, which is {_t}".format(_t=image_type_num2str(self.image_header.image_type)))
                    return False
        except Exception as err:
            print("Error: open file failed: {}".format(str(err)))
            return False

        return True

    def processOTAImage(self):
        if (self.image_header is None) or (self.app_content is None):
            print("No valid app image header or app conent found!!!")
            return False

        app_content_size_before_lzma = len(self.app_content)
        my_filter = [
            {
                "id": lzma.FILTER_LZMA1,
                "dict_size": 4*1024, # 4KB, (32KB max)
                "mode": lzma.MODE_NORMAL,
             },
        ]
        lzc = lzma.LZMACompressor(format=lzma.FORMAT_ALONE, filters=my_filter)
        out1 = lzc.compress(self.app_content)
        content_after_lzma = bytearray(b"".join([out1, lzc.flush()]))

        content_after_lzma[5] = get_num_at_byte(app_content_size_before_lzma, 0)
        content_after_lzma[6] = get_num_at_byte(app_content_size_before_lzma, 1)
        content_after_lzma[7] = get_num_at_byte(app_content_size_before_lzma, 2)
        content_after_lzma[8] = get_num_at_byte(app_content_size_before_lzma, 3)

        content_after_lzma[9] = 0
        content_after_lzma[10] = 0
        content_after_lzma[11] = 0
        content_after_lzma[12] = 0

        app_content_size_after_lzma = len(content_after_lzma)

        self.app_content = content_after_lzma
        crc32_after_lzma = zlib.crc32(content_after_lzma)

        self.image_header.image_type = IMAGE_TYPE_ORIGINAL_XZ
        ota_ver_major = self.image_header.getVerMajor()
        ota_ver_minor = self.image_header.getVerMinor()
        self.image_header.ver = ((ota_ver_major << 8) | ota_ver_minor) & 0xFFFF
        self.image_header.img_size_orig_xz = app_content_size_after_lzma
        self.image_header.img_crc32_orig_xz = crc32_after_lzma
        self.image_header.reCalcCRC32()

        return True

    def writeOTAImage(self):
        """
        OTA image, XZ format.
        """
        ota_filename = "{_a}-ota-xz-v{_ma}.{_mi}.bin" \
            .format(_a= os.path.basename(self.input_filepath).split(".")[0],
            _ma=self.image_header.getVerMajor(), _mi=self.image_header.getVerMinor())
        self.output_filepath = os.path.join(self.output_dir, ota_filename)

        if os.path.exists(self.output_filepath):
            shutil.rmtree(self.output_filepath, ignore_errors=True)

        try:
            with open(self.output_filepath, "wb") as fOutObj:
                fOutObj.write(self.image_header.toBytes())
                fOutObj.write(self.app_content)
        except Exception as err:
            print("Error: write file failed: {}".format(str(err)))
            return False

        if not os.path.exists(self.output_filepath):
            print("Failed to build: {_ota}".format(_ota=self.output_filepath))
            return False

        return True

    def doAllWork(self) -> bool:
        if not self.readPartTab():
            return False
        if not self.readAPP():
            return False
        if not self.processOTAImage():
            return False
        if not self.writeOTAImage():
            return False
        return True

    @property
    def input_filepath(self):
        return self.__input_filepath

    @input_filepath.setter
    def input_filepath(self, filepath):
        """
        Absolute filepath of flashimage.bin.
        """
        if isinstance(filepath, str):
            if os.path.exists(realpath(filepath)):
                self.__input_filepath = realpath(filepath)
            else:
                raise ValueError("not exist: {_f}".format(_f=filepath))
        else:
            raise TypeError("filepath MUST be a valid string")

    @property
    def output_dir(self):
        return self.__output_dir

    @output_dir.setter
    def output_dir(self, filepath):
        """
        Indicates the directory where to save ota.bin, normally it's the same
        directory as flashimage.bin.
        The output filename is `flashimage-ota-v{X}.{Y}.bin`, where X/Y is the
        major/minor version of flashimage.bin.
        """
        if isinstance(filepath, str):
            if os.path.exists(filepath):
                self.__output_dir = filepath
            else:
                raise ValueError("dir not exist: {_f}".format(_f=filepath))
        else:
            raise TypeError("dir MUST be a valid string")


if __name__ == "__main__":
    prog = os.path.basename(__file__)
    usage = ("\nargv1: /path/to/flashimage.bin \n"
            "Example: \n"
            "python3  {_p}  E:/ln_sdk/build/bin/flashimage.bin".format(_p=prog))

    parser = argparse.ArgumentParser(prog=prog, usage=usage)
    parser.add_argument("path_to_flashimage", help="absolute path of flashimage.bin")

    print(sys.argv)
    args = parser.parse_args()

    flashimage_filepath = args.path_to_flashimage
    ota_save_dir = os.path.dirname(flashimage_filepath)

    ota_tool = OTATOOL()
    ota_tool.input_filepath = flashimage_filepath
    ota_tool.output_dir     = ota_save_dir

    if not ota_tool.doAllWork():
        exit(-1)

    print("Succeed to build: {}".format(ota_tool.output_filepath))

    exit(0)

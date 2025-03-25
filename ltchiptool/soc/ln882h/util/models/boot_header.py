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

import zlib
import struct


class BootHeader:

    BOOT_HEADER_SIZE = (4 + 2 + 2 + 4 * 4)

    CRP_VALID_FLAG = 0x46505243

    BOOT_START_ADDR  = 0
    BOOT_SIZE_LIMIT  = (1024 * 24)

    def __init__(self, other_buf) -> None:
        self.__bootram_target_addr  = 0
        self.__bootram_bin_length   = 0 # 2bytes
        self.__bootram_crc_offset   = 0 # 2bytes
        self.__bootram_crc_value    = 0
        self.__bootram_vector_addr  = 0
        self.__crp_flag             = 0
        self.__boot_header_crc      = 0

        if not (isinstance(other_buf, bytearray) or isinstance(other_buf, bytes)):
            raise TypeError("Error: other_buf MUST be a bytearray or bytes!!!")

        if len(other_buf) < BootHeader.BOOT_HEADER_SIZE:
            raise ValueError("Error: other_buf MUST have at least {} bytes!!!".format(BootHeader.BOOT_HEADER_SIZE))

        self.__buffer = bytearray(BootHeader.BOOT_HEADER_SIZE)
        self.__buffer[:] = other_buf[0:BootHeader.BOOT_HEADER_SIZE]

        items = struct.unpack("<I2H4I", self.__buffer)
        self.__bootram_target_addr  = items[0]
        self.__bootram_bin_length   = items[1]
        self.__bootram_crc_offset   = items[2]
        self.__bootram_crc_value    = items[3]
        self.__bootram_vector_addr  = items[4]
        self.__crp_flag             = items[5]
        self.__boot_header_crc      = items[6]

    def toByteArray(self) -> bytearray:
        struct.pack_into("<I2H4I", self.__buffer, 0,
                        self.bootram_target_addr,
                        self.bootram_bin_length, self.bootram_crc_offset,
                        self.bootram_crc_value, self.bootram_vector_addr, self.crp_flag, self.boot_header_crc)
        self.__boot_header_crc = zlib.crc32(self.__buffer[0:(BootHeader.BOOT_HEADER_SIZE-4)])
        struct.pack_into("<I2H4I", self.__buffer, 0,
                        self.bootram_target_addr,
                        self.bootram_bin_length, self.bootram_crc_offset,
                        self.bootram_crc_value, self.bootram_vector_addr, self.crp_flag, self.boot_header_crc)
        return self.__buffer

    @property
    def bootram_target_addr(self):
        return self.__bootram_target_addr

    @property
    def bootram_bin_length(self):
        return self.__bootram_bin_length

    @bootram_bin_length.setter
    def bootram_bin_length(self, length):
        if isinstance(length, int):
            self.__bootram_bin_length = length
        else:
            raise TypeError("length MUST be int type!!!")

    @property
    def bootram_crc_offset(self):
        return self.__bootram_crc_offset

    @property
    def bootram_crc_value(self):
        return self.__bootram_crc_value

    @bootram_crc_value.setter
    def bootram_crc_value(self, val):
        if isinstance(val, int):
            self.__bootram_crc_value = val
        else:
            raise TypeError("crc MUST be int type!!!")

    @property
    def bootram_vector_addr(self):
        return self.__bootram_vector_addr

    @property
    def crp_flag(self):
        return self.__crp_flag

    @crp_flag.setter
    def crp_flag(self, crp):
        if isinstance(crp, int):
            if (crp == 0) or (crp == 1) or (crp == self.CRP_VALID_FLAG):
                self.__crp_flag = crp
            else:
                raise ValueError("Error: crp MUST be 0 or 1!!!")
        else:
            raise TypeError("Error: crp MUST be int type!!!")

    @property
    def boot_header_crc(self):
        self.__boot_header_crc = zlib.crc32(self.__buffer[0:(BootHeader.BOOT_HEADER_SIZE-4)])
        return self.__boot_header_crc

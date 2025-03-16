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
from .ln_tools import *
from .boot_header import BootHeader

# partition table start addr and size.
PARTITION_TAB_OFFSET    = BootHeader.BOOT_START_ADDR + BootHeader.BOOT_SIZE_LIMIT
PARTITION_TAB_SIZE      = 1024 * 4

PARTITION_DESC_INFO_SIZE = 4 + 4 + 4 + 4

PART_TYPE_APP          = 0
PART_TYPE_OTA          = 1
PART_TYPE_KV           = 2
PART_TYPE_NVDS         = 3
PART_TYPE_SIMU_EEPROM   = 4
PART_TYPE_USER         = 5
PART_TYPE_INVALID      = 6
PART_TYPE_BOOT         = 7
PART_TYPE_PART_TAB     = 8

__PART_TYPE_DICT = {
    PART_TYPE_APP          : "APP",
    PART_TYPE_OTA          : "OTA",
    PART_TYPE_KV           : "KV",
    PART_TYPE_NVDS         : "NVDS",
    PART_TYPE_SIMU_EEPROM  : "SIMU_EEPROM",
    PART_TYPE_USER         : "USER",
    PART_TYPE_INVALID      : "INVALID",
    PART_TYPE_BOOT         : "BOOT",
    PART_TYPE_PART_TAB     : "PART_TAB"
}


def part_type_num2str(type_num=PART_TYPE_INVALID):
    return __PART_TYPE_DICT.get(type_num, __PART_TYPE_DICT.get(PART_TYPE_INVALID))


def part_type_str2num(type_str):
    for k, v in __PART_TYPE_DICT.items():
        if v == type_str:
            return k
    return PART_TYPE_INVALID


class PartDescInfo(object):
    def __init__(self, parttype=0, startaddr=0, partsize=0, partcrc32=0):
        self.part_type  = parttype
        self.start_addr = startaddr
        self.part_size  = partsize
        self.__part_crc32 = partcrc32

        self.buffer     = bytearray(4 * 4)
        for i in range(0, 4 * 4):
            self.buffer[i] = 0

        self.toBytes()

    def toBytes(self) -> bytearray:
        self.buffer[0] = get_num_at_byte(self.part_type, 0)
        self.buffer[1] = get_num_at_byte(self.part_type, 1)
        self.buffer[2] = get_num_at_byte(self.part_type, 2)
        self.buffer[3] = get_num_at_byte(self.part_type, 3)

        self.buffer[4] = get_num_at_byte(self.start_addr, 0)
        self.buffer[5] = get_num_at_byte(self.start_addr, 1)
        self.buffer[6] = get_num_at_byte(self.start_addr, 2)
        self.buffer[7] = get_num_at_byte(self.start_addr, 3)

        self.buffer[8]  = get_num_at_byte(self.part_size, 0)
        self.buffer[9]  = get_num_at_byte(self.part_size, 1)
        self.buffer[10] = get_num_at_byte(self.part_size, 2)
        self.buffer[11] = get_num_at_byte(self.part_size, 3)

        self.reCalCRC32()

        return self.buffer

    def reCalCRC32(self):
        self.__part_crc32 = zlib.crc32(self.buffer[0:12])

        self.buffer[12] = get_num_at_byte(self.part_crc32, 0)
        self.buffer[13] = get_num_at_byte(self.part_crc32, 1)
        self.buffer[14] = get_num_at_byte(self.part_crc32, 2)
        self.buffer[15] = get_num_at_byte(self.part_crc32, 3)

    @property
    def part_type(self):
        return self.__part_type

    @part_type.setter
    def part_type(self, t):
        if isinstance(t, int):
            self.__part_type = t
        else:
            raise TypeError("part_type MUST be assigned to an int value (0~5)")

    @property
    def start_addr(self):
        return self.__start_addr

    @start_addr.setter
    def start_addr(self, addr):
        if isinstance(addr, int):
            self.__start_addr = addr
        else:
            raise TypeError("start_addr MUST be assigned to an int value")

    @property
    def part_size(self):
        return self.__part_size

    @part_size.setter
    def part_size(self, s):
        if isinstance(s, int):
            self.__part_size = s
        else:
            raise TypeError("part_size MUST be assigned to an int value")

    @property
    def part_crc32(self):
        return self.__part_crc32

    # readonly
    # @part_crc32.setter
    # def part_crc32(self, crc32):
    #     if isinstance(crc32, int):
    #         self.__part_crc32 = crc32
    #     else:
    #         raise TypeError("part_crc32 MUST be assigned to an int value")

    def __str__(self) -> str:
        output = ("partition_type: {_p:>12}, start_addr: 0x{_sa:08X}, size_KB: 0x{_sz:08X}, crc32: 0x{_c:08X}"
                    .format(_p=part_type_num2str(self.part_type), _sa=self.start_addr, _sz=self.part_size, _c=self.part_crc32))
        return output

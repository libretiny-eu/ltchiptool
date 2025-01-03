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

import os
import sys


def realpath(path):
    return os.path.normcase(os.path.realpath(path))


def get_num_at_byte(num, index):
    """
    Get one byte from a 32-bit number (little-endian), the index is [0, 3].
    For exame:
    num = 0x12345678
    byte 0 is 0x78
    byte 1 is 0x56
    byte 2 is 0x34
    byte 3 is 0x12
    """
    shift = index % 4
    val = 0xFF & ( num >> (8*shift) )
    return val


def dump_bytes_in_hex(byte_arr=None, lineSize=16, bytesMax=256, title=""):
    """
    Print byte array in hex format.
    lineSize: print how many items each line.
    bytesMax: print how many items at most. (-1, print the whole byte array.)
    title:
    """

    if title:
        print("\n----------  {}  ----------".format(title))

    if bytesMax == -1:
        bytesMax = len(byte_arr)
    elif bytesMax > len(byte_arr):
        bytesMax = len(byte_arr)
    else:
        pass

    for cnt in range(0, bytesMax):
        if cnt % lineSize == 0:
            print("{_so:08X} |".format(_so=cnt), end=" ")
        print("{_b:02X}".format(_b=byte_arr[cnt]), end=" ")
        if cnt % lineSize == (lineSize-1):
            print("")


def check_python_version():
    major = sys.version_info.major
    minor = sys.version_info.minor
    if (major == 3) and (minor >= 6):
        return True
    else:
        print('WARNING: Python 2 or Python 3 versions older than 3.6 are not supported.', file=sys.stderr)
        exit(-100)
    return False

#  Copyright (c) Kuba Szczodrzyński 2022-07-22.

from enum import IntEnum


class ImageType(IntEnum):
    PARTAB = 0
    BOOT = 1
    FWHS_S = 2
    FWHS_NS = 3
    FWLS = 4
    ISP = 5
    VOE = 6
    WLN = 7
    XIP = 8
    CPFW = 9
    WOWLN = 10
    CINIT = 11


class PartitionType(IntEnum):
    PARTAB = 0
    BOOT = 1
    SYS = 2
    CAL = 3
    USER = 4
    FW1 = 5
    FW2 = 6
    VAR = 7
    MP = 8
    RDP = 9


class SectionType(IntEnum):
    DTCM = 0x80
    ITCM = 0x81
    SRAM = 0x82
    PSRAM = 0x83
    LPDDR = 0x84
    XIP = 0x85


class EncAlgo(IntEnum):
    AES_EBC = 0
    AES_CBC = 1
    OTHER = 0xFF


class HashAlgo(IntEnum):
    MD5 = 0
    SHA256 = 1
    OTHER = 0xFF

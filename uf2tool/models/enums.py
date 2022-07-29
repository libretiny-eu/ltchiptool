# Copyright (c) Kuba Szczodrzyński 2022-05-27.

from enum import IntEnum


class Tag(IntEnum):
    VERSION = 0x9FC7BC  # version of firmware file - UTF8 semver string
    PAGE_SIZE = 0x0BE9F7  # page size of target device (32 bit unsigned number)
    SHA2 = 0xB46DB0  # SHA-2 checksum of firmware (can be of various size)
    DEVICE = 0x650D9D  # description of device (UTF8)
    DEVICE_ID = 0xC8A729  # device type identifier
    # LibreTuya custom tags
    OTA_VERSION = 0x5D57D0  # format version
    BOARD = 0xCA25C8  # board name (lowercase code)
    FIRMWARE = 0x00DE43  # firmware description / name
    BUILD_DATE = 0x822F30  # build date/time as Unix timestamp
    LT_VERSION = 0x59563D  # LT version (semver)
    LT_PART_1 = 0x805946  # OTA1 partition name
    LT_PART_2 = 0xA1E4D7  # OTA2 partition name
    LT_HAS_OTA1 = 0xBBD965  # image has any data for OTA1
    LT_HAS_OTA2 = 0x92280E  # image has any data for OTA2
    LT_BINPATCH = 0xB948DE  # binary patch to convert OTA1->OTA2


class Opcode(IntEnum):
    DIFF32 = 0xFE  # difference between 32-bit values

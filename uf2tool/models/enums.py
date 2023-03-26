# Copyright (c) Kuba Szczodrzyński 2022-05-27.

from enum import Enum, IntEnum

import click


class Tag(IntEnum):
    VERSION = 0x9FC7BC  # version of firmware file - UTF8 semver string
    PAGE_SIZE = 0x0BE9F7  # page size of target device (32 bit unsigned number)
    SHA2 = 0xB46DB0  # SHA-2 checksum of firmware (can be of various size)
    DEVICE = 0x650D9D  # description of device (UTF8)
    DEVICE_ID = 0xC8A729  # device type identifier
    # format versions
    OTA_FORMAT_1 = 0x5D57D0
    OTA_FORMAT_2 = 0x6C8492
    # LibreTuya custom tags
    OTA_PART_LIST = 0x6EC68A  # list of OTA schemes this package is usable in
    OTA_PART_INFO = 0xC0EE0C  # partition names for each OTA schemes
    BOARD = 0xCA25C8  # board name (lowercase code)
    FIRMWARE = 0x00DE43  # firmware description / name
    BUILD_DATE = 0x822F30  # build date/time as Unix timestamp
    BINPATCH = 0xB948DE  # binary patch to convert OTA1->OTA2
    FAL_PTABLE = 0x8288ED  # FAL partition table
    LT_VERSION = 0x59563D  # LT version (semver)
    # legacy tags
    LT_LEGACY_PART_1 = 0x805946  # OTA1 partition name
    LT_LEGACY_PART_2 = 0xA1E4D7  # OTA2 partition name
    LT_LEGACY_HAS_OTA1 = 0xBBD965  # image has any data for OTA1
    LT_LEGACY_HAS_OTA2 = 0x92280E  # image has any data for OTA2


class ImageTarget(Enum):
    DEVICE = "device"
    FLASHER = "flasher"


class OTAScheme(IntEnum):
    DEVICE_SINGLE = 0
    DEVICE_DUAL_1 = 1
    DEVICE_DUAL_2 = 2
    FLASHER_SINGLE = 3
    FLASHER_DUAL_1 = 4
    FLASHER_DUAL_2 = 5


class OTASchemeParamType(click.ParamType):
    name = "SCHEME"

    def convert(self, value, param, ctx) -> OTAScheme:
        scheme_map = {
            "device": OTAScheme.DEVICE_SINGLE,
            "device1": OTAScheme.DEVICE_DUAL_1,
            "device2": OTAScheme.DEVICE_DUAL_2,
            "flasher": OTAScheme.FLASHER_SINGLE,
            "flasher1": OTAScheme.FLASHER_DUAL_1,
            "flasher2": OTAScheme.FLASHER_DUAL_2,
        }
        try:
            return scheme_map[value]
        except KeyError as e:
            self.fail(f"Scheme must be one of: {', '.join(scheme_map.keys())}")


class Opcode(IntEnum):
    DIFF32 = 0xFE  # difference between 32-bit values

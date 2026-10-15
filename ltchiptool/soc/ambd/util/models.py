# Copyright (c) Bl00d-B0b 2026-08-06.

"""AmebaD (RTL8720D) image structures (vendor SDK gnu_utility/prepend_header.sh,
prepend_ota_header.sh and project_hp/asdk Makefile, ameba-rtos-d).

Every section binary carries a 32-byte prepend header; the flash image is a
plain concatenation when RSIP/RDP/SBOOT are off (BW16 default); the OTA payload
(km0_km4_image2) gets an extra "OTA1" header.
"""

import struct
from dataclasses import dataclass

# Section header signatures
IMG2_SIGN = b"81958711"  # 8 ASCII bytes, all non-boot images
BOOT_PATTERN_1 = 0x99999696  # boot RAM (ram_1.bin), big-endian
BOOT_PATTERN_2 = 0x3FCC66FC

# Flash layout, measured from a BW16 (RTL8720DN, 4MB) factory dump:
# 0x000000 km4_boot | 0x004000 km0_boot | 0x005000 system data |
# 0x006000 OTA1 | 0x200000 littlefs | 0x206000 OTA2
AMBD_KM4_BOOT_OFFSET = 0x000000
AMBD_KM0_BOOT_OFFSET = 0x004000
AMBD_OTA1_OFFSET = 0x006000
AMBD_OTA2_OFFSET_4MB = 0x206000  # 2MB parts use 0x106000 (vendor OTA_Change)

# Section load-address bases seen in the image headers
AMBD_BOOT_ADDRESS = 0x08000000  # km4_boot XIP
AMBD_KM0_XIP_ADDRESS = 0x0C000000  # KM0 image2 XIP
AMBD_KM4_XIP_ADDRESS = 0x0E000000  # KM4 image2 XIP

OTA_SIGN = 0x4F544131  # "OTA1"
OTA_HEADER_LEN = 24


@dataclass
class SectionHeader:
    """32-byte header prepended to every section binary.

    Layout: sign[8] | length u32le | address u32le | reserved 16 x 0xFF.
    Boot RAM sections use the two boot patterns (big-endian) as the sign.
    """

    length: int
    address: int
    boot: bool = False

    def pack(self) -> bytes:
        if self.boot:
            sign = struct.pack(">II", BOOT_PATTERN_1, BOOT_PATTERN_2)
        else:
            sign = IMG2_SIGN
        return sign + struct.pack("<II", self.length, self.address) + b"\xff" * 16

    @classmethod
    def unpack(cls, data: bytes) -> "SectionHeader":
        if len(data) < 32:
            raise ValueError("AmebaD section header is 32 bytes")
        boot = data[0:8] == struct.pack(">II", BOOT_PATTERN_1, BOOT_PATTERN_2)
        if not boot and data[0:8] != IMG2_SIGN:
            raise ValueError("Not an AmebaD section header")
        length, address = struct.unpack_from("<II", data, 8)
        return cls(length=length, address=address, boot=boot)


def pack_section(payload: bytes, address: int, boot: bool = False) -> bytes:
    return SectionHeader(len(payload), address, boot).pack() + payload

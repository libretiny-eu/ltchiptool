#  Copyright (c) 2026 bavci1988.

"""XRadio AWIH images.

The SDK's mkimage tool chains one AWIH section per binary. The BOOT header also
tells the ROM where the boot selection sector (FDCM) and the compressed update
slot are; mkimage leaves those fields unset, so make_image() fills them in.

make_ota_image() builds the network update: the APP section chain, compressed
with XZ into one AWIH section. The bootloader unpacks it into the APP area on
the next boot.
"""

from __future__ import annotations

import lzma
import struct
from dataclasses import dataclass
from typing import List, Optional, Tuple

HEADER = struct.Struct("<IIHH7I6I")
AWIH_MAGIC = 0x48495741
AWIH_VERSION = 5
NO_NEXT = 0xFFFFFFFF
# project/bootloader/main.c: BL_DEC_IMG_DICT_MAX
BOOTLOADER_XZ_DICT = 8 * 1024
MAX_SECTIONS = 32
SECTOR_BYTES = 4096
# mkimage starts every section after the first one on a 1 KiB boundary
SECTION_ALIGN = 1024

ID_BOOT = 0xA5FF5A00
ID_APP = 0xA5FE5A01
ID_APP_XIP = 0xA5FD5A02
ID_WLAN_BL = 0xA5FA5A05
ID_WLAN_FW = 0xA5F95A06
ID_SYS_SDD = 0xA5F85A07

# Header field indexes in HEADER
_MAGIC, _VERSION, _HEAD_SUM, _DATA_SUM, _DATA_SIZE = range(5)
_LOAD_ADDR, _ENTRY, _BODY_LEN = 5, 6, 7
_ATTRIBUTE, _NEXT, _ID, _PRIV0, _PRIV1, _PRIV2 = 8, 9, 10, 11, 12, 13
_ATTR_XZ_APP = 0x11


@dataclass
class Section:
    id: int
    data: bytes
    attr: int
    load_addr: int = NO_NEXT
    entry: int = NO_NEXT
    # flash offset; None places the section after the previous one
    offset: Optional[int] = None


@dataclass(frozen=True)
class Layout:
    app_offset: int
    ota_cfg_offset: int
    ota_cfg_size: int
    image_limit: int
    xz_slot_size: int


def checksum16(data: bytes) -> int:
    """The ROM image checksum: sum of little-endian 16-bit words, modulo 65536."""
    if len(data) % 2:
        data += b"\x00"
    return sum(struct.unpack(f"<{len(data) // 2}H", data)) & 0xFFFF


def _pack_header(fields: List[int]) -> bytes:
    fields[_HEAD_SUM] = 0
    fields[_HEAD_SUM] = (0xFFFF - checksum16(HEADER.pack(*fields))) & 0xFFFF
    return HEADER.pack(*fields)


def read_section(
    data: bytes,
    offset: int,
    expected_id: Optional[int] = None,
) -> Tuple[int, ...]:
    """Return the header fields of the AWIH section at offset after checking it."""
    if offset < 0 or offset + HEADER.size > len(data):
        raise ValueError(f"AWIH header out of bounds at 0x{offset:X}")
    fields = HEADER.unpack_from(data, offset)
    if (
        fields[_MAGIC] != AWIH_MAGIC
        or fields[_VERSION] != AWIH_VERSION
        or checksum16(data[offset : offset + HEADER.size]) != 0xFFFF
    ):
        raise ValueError(f"Invalid AWIH header at 0x{offset:X}")
    if expected_id is not None and fields[_ID] != expected_id:
        raise ValueError(f"Unexpected AWIH section 0x{fields[_ID]:08X} at 0x{offset:X}")
    size = fields[_DATA_SIZE]
    body = offset + HEADER.size
    if not size or body + size > len(data):
        raise ValueError(f"Invalid AWIH body length at 0x{offset:X}")
    if (checksum16(data[body : body + size]) + fields[_DATA_SUM]) & 0xFFFF != 0xFFFF:
        raise ValueError(f"AWIH body checksum mismatch at 0x{offset:X}")
    return fields


def check_layout(layout: Layout, flash_size: int) -> None:
    """Reject a layout that the bootloader cannot use safely."""
    if layout.ota_cfg_size != SECTOR_BYTES or layout.ota_cfg_offset % SECTOR_BYTES:
        raise ValueError("The OTA config (FDCM) must be one aligned 4 KiB sector")
    if layout.app_offset % SECTOR_BYTES or layout.app_offset < SECTOR_BYTES:
        raise ValueError("Bad bootloader/application boundary")
    if layout.image_limit != layout.ota_cfg_offset:
        raise ValueError("The app partition must end at the OTA config sector")
    if layout.xz_slot_size % 1024 or layout.xz_slot_size > 0xFFFF * 1024:
        raise ValueError("Invalid download partition size")
    if layout.image_limit % 1024 or layout.image_limit > 0xFFFF * 1024:
        raise ValueError("Invalid app partition end")
    end = layout.ota_cfg_offset + layout.ota_cfg_size + layout.xz_slot_size
    if end > flash_size:
        raise ValueError("The download partition does not fit the flash")


def make_image(sections: List[Section], layout: Layout, flash_size: int) -> bytes:
    """Chain the sections like mkimage, with the OTA layout in the BOOT header."""
    check_layout(layout, flash_size)
    if not sections or sections[0].id != ID_BOOT or sections[1].id != ID_APP:
        raise ValueError("The image must start with the BOOT and APP sections")
    sections[1].offset = layout.app_offset

    offsets = []
    cursor = 0
    for section in sections:
        if section.offset is not None:
            if section.offset < cursor:
                raise ValueError(f"Section 0x{section.id:08X} overlaps its predecessor")
            cursor = section.offset
        offsets.append(cursor)
        cursor += HEADER.size + len(section.data)
        cursor = (cursor + SECTION_ALIGN - 1) // SECTION_ALIGN * SECTION_ALIGN
    end = offsets[-1] + HEADER.size + len(sections[-1].data)
    if end > layout.image_limit:
        raise ValueError(
            f"Firmware of {end} bytes does not fit the app partition "
            f"(ends at 0x{layout.image_limit:X})"
        )

    image = bytearray(b"\xff" * end)
    for i, section in enumerate(sections):
        next_addr = offsets[i + 1] if i + 1 < len(sections) else NO_NEXT
        priv = [NO_NEXT] * 6
        if section.id == ID_BOOT:
            # flash 0xFF: the OTA config is on the same flash as the image
            priv[0] = (layout.ota_cfg_size << 8) | 0xFF
            priv[1] = layout.ota_cfg_offset
            priv[2] = ((layout.xz_slot_size // 1024) << 16) | (
                layout.image_limit // 1024
            )
        fields = [
            AWIH_MAGIC,
            AWIH_VERSION,
            0,
            (0xFFFF - checksum16(section.data)) & 0xFFFF,
            len(section.data),
            section.load_addr,
            section.entry,
            len(section.data),
            section.attr,
            next_addr,
            section.id,
            *priv,
        ]
        offset = offsets[i]
        image[offset : offset + HEADER.size] = _pack_header(fields)
        image[offset + HEADER.size : offset + HEADER.size + len(section.data)] = (
            section.data
        )
    image = bytes(image)
    read_section(image, 0, ID_BOOT)
    return image


def make_ota_image(firmware: bytes, flash_size: int) -> bytes:
    """Compress the APP section chain of a firmware image into an AWIH/XZ update."""
    boot = read_section(firmware, 0, ID_BOOT)
    app_start = boot[_NEXT]
    metadata = boot[_PRIV1]
    image_limit = (boot[_PRIV2] & 0xFFFF) * 1024
    slot = (boot[_PRIV2] >> 16) * 1024
    if not app_start or app_start == NO_NEXT or app_start % SECTOR_BYTES:
        raise ValueError("Bad bootloader/application boundary")
    if metadata % SECTOR_BYTES or metadata <= app_start or metadata >= flash_size:
        raise ValueError("Invalid FDCM address in BOOT header")
    if not slot or metadata + SECTOR_BYTES + slot > flash_size:
        raise ValueError("Compressed slot outside physical flash")
    if image_limit <= app_start or image_limit > metadata:
        raise ValueError("Image limit overlaps FDCM")

    cursor = app_start
    sections = 0
    while True:
        fields = read_section(firmware, cursor, ID_APP if sections == 0 else None)
        sections += 1
        if sections > MAX_SECTIONS:
            raise ValueError("Too many AWIH sections")
        end = cursor + HEADER.size + fields[_DATA_SIZE]
        if end > image_limit:
            raise ValueError("Firmware does not fit the active image area")
        successor = fields[_NEXT]
        if successor == NO_NEXT:
            break
        if successor < end or successor % 4:
            raise ValueError("Invalid AWIH next_addr")
        cursor = successor

    raw = firmware[app_start:end]
    payload = lzma.compress(
        raw,
        format=lzma.FORMAT_XZ,
        check=lzma.CHECK_CRC32,
        filters=[
            {"id": lzma.FILTER_LZMA2, "dict_size": BOOTLOADER_XZ_DICT, "preset": 6}
        ],
    )
    fields = [
        AWIH_MAGIC,
        AWIH_VERSION,
        0,
        (0xFFFF - checksum16(payload)) & 0xFFFF,
        len(payload),
    ]
    fields += [NO_NEXT, NO_NEXT, len(payload), _ATTR_XZ_APP, NO_NEXT, ID_APP]
    fields += [NO_NEXT] * 6
    output = _pack_header(fields) + payload
    if len(output) > slot:
        raise ValueError(
            f"OTA image of {len(output)} bytes does not fit "
            f"the {slot} byte download partition"
        )
    read_section(output, 0, ID_APP)
    if lzma.decompress(payload) != raw:
        raise ValueError("XZ round trip changed the image")
    return output

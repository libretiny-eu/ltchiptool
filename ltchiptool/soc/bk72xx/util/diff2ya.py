# Copyright (c) Kuba Szczodrzyński 2026-04-03.

import lzma
from dataclasses import dataclass
from enum import IntEnum
from typing import IO
from zlib import crc32

from datastruct import DataStruct, datastruct
from datastruct.fields import (
    checksum_end,
    checksum_field,
    checksum_start,
    const,
    field,
    padding,
)

from ltchiptool.util.intbin import ByteGenerator


class Diff2yaBinType(IntEnum):
    SINGLE = 0x53494E47
    AB_1 = 0x41425349
    AB_2 = 0x41425238
    COMPRESS = 0x4C5A4350
    AB_3 = 0x4C5A4352
    AB_4 = 0x4C5A4351


@dataclass
@datastruct(padding_pattern=b"\x00")
class Diff2yaHeader(DataStruct):
    magic: int = const(0x4D4D4D)(field("I"))
    bin_type: Diff2yaBinType = field("I")
    src_crc32: int = field("I")
    dst_crc32: int = field("I")
    src_len: int = field("I")
    dst_len: int = field("I")
    bin_offset: int = field("I", default=64)
    bin_start_addr: int = field("I", default=0)
    compress_len: int = field("I")
    compress_crc32: int = field("I")
    step: int = field("I", default=0)
    buf_size: int = field("I", default=0x10000)
    mode: int = field("B", default=0)
    file_index: int = field("B", default=0)
    min_supp_ver: int = field("H", default=2)
    attr1: int = field("I", default=0)
    attr2: int = field("I", default=0)
    extend_len: int = field("I")


@dataclass
@datastruct(padding_pattern=b"\x00")
class Diff2yaExtend(DataStruct):
    extend_type: int = field("I", default=0)
    ability: int = field("I", default=0x40)
    src_bin_len: int = field("I")
    dst_bin_len: int = field("I")
    part_b_crc: int = field("I")
    _1: ... = padding(124)


@dataclass
@datastruct(padding_pattern=b"\x00")
class Diff2yaManage(DataStruct):
    magic: int = const(0xABCDDCBA)(field("I"))
    crc32: int = checksum_field("crc32")(field("I", default=0))
    _crc_start: ... = checksum_start(
        init=lambda ctx: 0,
        update=lambda value, obj, ctx: obj + sum(value),
        end=lambda value, ctx: value,
        target=crc32,
    )
    patchsz: int = field("I")
    wrcnt: int = field("I", default=0)
    ctrlid: int = field("I", default=0)
    flitoff: int = field("I", default=0)
    blockid: int = field("B", default=0)
    state: int = field("B", default=1)
    is_confirm_addr: bool = field("B", default=False)
    recover_type: int = field("B", default=0)
    flh_start_addr: int = field("I")
    flh_len: int = field("I")
    backup_confirm_addr: int = field("I", default=0)
    patch_confirm_addr: int = field("I", default=0)
    attr1: int = field("I", default=0)
    ability: int = field("I", default=1)
    part_b_crc: int = field("I")
    _1: ... = padding(8)
    _crc_end: ... = checksum_end(_crc_start)


def diff2ya_package(f: IO[bytes]) -> ByteGenerator:
    data = f.read()
    xz_data = lzma.compress(
        data=data,
        format=lzma.FORMAT_XZ,
        check=lzma.CHECK_CRC32,
        filters=[
            dict(
                id=lzma.FILTER_LZMA2,
                dict_size=4096,
                depth=0,
                mode=lzma.MODE_NORMAL,
                nice_len=273,
                lc=3,
                lp=0,
                pb=2,
                mf=lzma.MF_BT4,
            )
        ],
    )

    header = Diff2yaHeader(
        bin_type=Diff2yaBinType.COMPRESS,
        src_crc32=crc32(data),
        dst_crc32=crc32(data),
        src_len=len(data),
        dst_len=len(data),
        compress_len=len(xz_data),
        compress_crc32=crc32(xz_data),
        extend_len=0x0,
    ).pack()
    yield header
    yield xz_data


def diff2ya_package_info(
    ota_offs: int,
    ota_len: int,
    flh_len: int = 0x1D2000,
    flh_start: int = 0x10000,
) -> bytes:
    # flh_start: logical app address (without CRC16), where the bootloader writes it
    # flh_len: Tuya's application area size, only used by the bootloader's size check
    return Diff2yaManage(
        patchsz=ota_len,
        is_confirm_addr=True,
        flh_start_addr=flh_start,
        flh_len=flh_len,
        patch_confirm_addr=ota_offs,
        part_b_crc=0x0,
    ).pack()

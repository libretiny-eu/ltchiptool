#  Copyright (c) Kuba Szczodrzyński 2023-1-4.

from dataclasses import dataclass
from enum import IntEnum
from typing import List

from datastruct import Context, DataStruct
from datastruct.fields import (
    action,
    adapter,
    align,
    alignto,
    bitfield,
    built,
    field,
    packing,
    padding,
    repeat,
    subfield,
)

from .enums import FlashSize, FlashSpeed, PartitionType
from .headers import FST, EntryHeader, SectionHeader, header_is_last
from .utils import FF_16, FF_32, FF_48, BitFlag, index


@dataclass
class TrapConfig:
    is_valid: bool
    level: int
    port: int
    pin: int


@dataclass
class PartitionRecord(DataStruct):
    offset: int = field("I")
    length: int = field("I")
    type: PartitionType = field("B")
    dbg_skip: bool = field("?", default=False)
    _1: ... = padding(6)
    hash_key_valid: bool = adapter(BitFlag())(
        built("B", lambda ctx: ctx.type == PartitionType.BOOT or ctx.hash_key != FF_32),
    )
    _2: ... = padding(15)
    hash_key: bytes = field("32s", default=FF_32)


def find_partition_index(type: PartitionType):
    return lambda ctx: index(lambda p: p.type == type, ctx.partitions, 255)


@dataclass
class PartitionTable(DataStruct):
    class KeyExport(IntEnum):
        NONE = 0
        LATEST = 1
        BOTH = 2

    rma_w_state: int = field("B", default=0xF0)
    rma_ov_state: int = field("B", default=0xF0)
    e_fwv: int = field("B", default=0)
    _1: ... = padding(1)
    count: int = built("B", lambda ctx: len(ctx.partitions) - 1)
    idx_fw1: int = built("B", find_partition_index(PartitionType.FW1))
    idx_fw2: int = built("B", find_partition_index(PartitionType.FW2))
    idx_var: int = built("B", find_partition_index(PartitionType.VAR))
    idx_mp: int = built("B", find_partition_index(PartitionType.MP))
    _2: ... = padding(1)
    trap_ota: TrapConfig = bitfield("b1p6u1u3u5", TrapConfig, default=0)
    trap_mp: TrapConfig = bitfield("b1p6u1u3u5", TrapConfig, default=0)
    _3: ... = padding(1)
    key_export: KeyExport = field("B", default=KeyExport.BOTH)
    user_data_len: int = built("H", lambda ctx: len(ctx.user_data))
    _4: ... = padding(14)
    partitions: List[PartitionRecord] = repeat(lambda ctx: ctx.count + 1)(subfield())
    user_data: bytes = field(lambda ctx: ctx.user_data_len, default=b"")


@dataclass
class SystemData(DataStruct):
    @dataclass
    class ForceOldOTA:
        is_active: bool
        port: int
        pin: int

    # OTA section
    _1: ... = alignto(0x08 + 3)
    force_old_ota: ForceOldOTA = bitfield("b1P1u1u5", ForceOldOTA, 0xFF)
    # Flash section
    _2: ... = alignto(0x22)
    flash_speed: FlashSpeed = field("H", default=FlashSpeed.QIO)
    flash_size: FlashSize = field("H", default=FlashSize.F_2MB)
    flash_id: bytes = field("3s", default=b"\xFF\xFF\xFF")
    # Log UART section
    _3: ... = alignto(0x30)
    baudrate: int = adapter(
        encode=lambda v, ctx: 0xFFFFFFFF if v == 115200 else v,
        decode=lambda v, ctx: 115200 if v == 0xFFFFFFFF else v,
    )(field("I", default=115200))
    # Calibration data
    _4: ... = alignto(0x40)
    spic_calibration: bytes = field("48s", default=FF_48)
    _5: ... = alignto(0xFE0)
    bt_ftl_gc_status: int = field("I", default=0xFFFFFFFF)
    _6: ... = alignto(0xFF0)
    bt_calibration: bytes = field("16s", default=FF_16)


@dataclass
class Bootloader(DataStruct):
    entry: EntryHeader = subfield()
    data: bytes = field(lambda ctx: ctx.entry.length, default=b"")
    _1: ... = align(0x20, False, pattern=b"\x00")


@dataclass
class Section(DataStruct):
    # noinspection PyMethodParameters
    def update(ctx: Context):
        section: "Section" = ctx.self
        if section.header.next_offset == 0:
            # calculate next_offset
            size = section.sizeof(**ctx.P.kwargs)
            section.header.next_offset = size

    _0: ... = action(packing(update))
    header: SectionHeader = subfield()
    entry: EntryHeader = subfield()
    data: bytes = field(lambda ctx: ctx.entry.length, default=b"")
    _1: ... = align(0x20, False, pattern=b"\x00")


@dataclass
class Firmware(DataStruct):
    # noinspection PyMethodParameters
    def update(ctx: Context):
        firmware: "Firmware" = ctx.self
        # set next_offset to 0 for all images but the last,
        # to allow calculation by Section.update()
        for section in firmware.sections:
            section.header.next_offset = 0
        firmware.sections[-1].header.next_offset = 0xFFFFFFFF

    _0: ... = action(packing(update))
    fst: FST = subfield()
    sections: List[Section] = repeat(last=header_is_last)(subfield())

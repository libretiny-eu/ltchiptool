#  Copyright (c) Kuba Szczodrzyński 2023-11-3.

from dataclasses import dataclass
from enum import IntEnum

from datastruct import DataStruct
from datastruct.fields import adapter, alignto, bitfield, field

FF_16 = b"\xFF" * 16


class FlashSpeed(IntEnum):
    F_100MHZ = 0xFFFF
    F_83MHZ = 0x7FFF
    F_71MHZ = 0x3FFF
    F_62MHZ = 0x1FFF
    F_55MHZ = 0x0FFF
    F_50MHZ = 0x07FF
    F_45MHZ = 0x03FF


class FlashMode(IntEnum):
    QIO = 0xFFFF  # Quad IO
    QO = 0x7FFF  # Quad Output
    DIO = 0x3FFF  # Dual IO
    DO = 0x1FFF  # Dual Output
    SINGLE = 0x0FFF  # One IO


@dataclass
class SystemData(DataStruct):
    @dataclass
    class ForceOldOTA:
        is_disabled: bool
        port: int
        pin: int

    @dataclass
    class RSIPMask:
        length: int
        offset: int
        is_disabled: bool

    # OTA section
    ota2_address: int = field("I", default=0xFFFFFFFF)
    ota2_switch: int = field("I", default=0xFFFFFFFF)
    force_old_ota: ForceOldOTA = bitfield("b1P1u1u5", ForceOldOTA, 0xFF)
    # RDP section (AmebaZ only)
    _1: ... = alignto(0x10)
    rdp_address: int = field("I", default=0xFFFFFFFF)
    rdp_length: int = field("I", default=0xFFFFFFFF)
    # Flash section
    _2: ... = alignto(0x20)
    flash_mode: FlashMode = field("H", default=FlashMode.QIO)
    flash_speed: FlashSpeed = field("H", default=FlashSpeed.F_100MHZ)  # AmebaZ only
    flash_id: int = field("H", default=0xFFFF)
    flash_size_mb: int = adapter(
        encode=lambda v, ctx: 0xFFFF if v == 2 else (v << 10) - 1,
        decode=lambda v, ctx: 2 if v == 0xFFFF else (v + 1) >> 10,
    )(field("H", default=2))
    flash_status: int = field("H", default=0x0000)
    # Log UART section
    _3: ... = alignto(0x30)
    baudrate: int = adapter(
        encode=lambda v, ctx: 0xFFFFFFFF if v == 115200 else v,
        decode=lambda v, ctx: 115200 if v == 0xFFFFFFFF else v,
    )(field("I", default=115200))
    # Calibration data (AmebaZ2 only)
    _4: ... = alignto(0x40)
    spic_calibration: bytes = field("16s", default=FF_16)
    # RSIP section (AmebaZ only)
    _5: ... = alignto(0x50)
    rsip_mask1: RSIPMask = bitfield("u7P2u22u1", RSIPMask, 0xFFFFFFFF)
    rsip_mask2: RSIPMask = bitfield("u7P2u22u1", RSIPMask, 0xFFFFFFFF)
    # Calibration data (AmebaZ2 only)
    _6: ... = alignto(0xFE0)
    bt_ftl_gc_status: int = field("I", default=0xFFFFFFFF)
    _7: ... = alignto(0xFF0)
    bt_calibration: bytes = field("16s", default=FF_16)

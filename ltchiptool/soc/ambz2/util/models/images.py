#  Copyright (c) Kuba Szczodrzyński 2023-1-19.

from dataclasses import dataclass
from hashlib import sha256
from hmac import HMAC
from typing import Any, List

from datastruct import Context, DataStruct, sizeof
from datastruct.fields import (
    action,
    align,
    alignto,
    checksum_end,
    checksum_field,
    checksum_start,
    cond,
    field,
    packing,
    repeat,
    subfield,
    switch,
)

from .headers import ImageHeader, Keyblock, KeyblockOTA, header_is_last
from .partitions import Bootloader, Firmware, PartitionTable, SystemData
from .utils import FF_32

FLASH_CALIBRATION = b"\x99\x99\x96\x96\x3F\xCC\x66\xFC\xC0\x33\xCC\x03\xE5\xDC\x31\x62"


@dataclass
class Image(DataStruct):
    # noinspection PyMethodParameters
    def update(ctx: Context):
        image: "Image" = ctx.self
        if image.header.next_offset == 0:
            # calculate next_offset
            size = image.sizeof(**ctx.P.kwargs)
            if ctx.is_first and ctx.is_ota:
                size -= sizeof(image.ota_signature)
            if ctx.is_first:
                size -= sizeof(image.keyblock)
            image.header.next_offset = size
        if ctx.is_first and ctx.is_ota:
            # calculate OTA signature (header hash)
            header = image.header.pack(parent=image)
            if ctx.hash_key:
                image.ota_signature = HMAC(
                    key=ctx.hash_key,
                    msg=header,
                    digestmod=sha256,
                ).digest()
            else:
                image.ota_signature = sha256(header).digest()

    _0: ... = action(packing(update))
    _hash: ... = checksum_start(
        init=lambda ctx: HMAC(ctx.hash_key, digestmod=sha256)
        if ctx.hash_key
        else sha256(),
        update=lambda data, obj, ctx: obj.update(data),
        end=lambda obj, ctx: obj.digest(),
    )

    # 'header' hash for firmware images
    ota_signature: bytes = cond(lambda ctx: ctx.is_first and ctx.is_ota)(
        field("32s", default=FF_32)
    )
    # keyblock for first sub-image only
    keyblock: Any = cond(lambda ctx: ctx.is_first)(
        switch(lambda ctx: ctx.is_ota)(
            false=(Keyblock, subfield()),
            true=(KeyblockOTA, subfield()),
        )
    )

    header: ImageHeader = subfield()
    data: Any = switch(lambda ctx: ctx.header.type)(
        PARTAB=(PartitionTable, subfield()),
        BOOT=(Bootloader, subfield()),
        # OTA images
        FWHS_S=(Firmware, subfield()),
        FWHS_NS=(Firmware, subfield()),
        FWLS=(Firmware, subfield()),
        XIP=(Firmware, subfield()),
        # something else?
        default=(bytes, field(lambda ctx: ctx.header.length)),
    )

    _1: ... = checksum_end(_hash)
    hash: bytes = checksum_field("Image hash")(field("32s", default=FF_32))
    # align to 0x4000 for images having next_offset, 0x40 otherwise
    # skip offset for non-firmware images
    _2: ... = cond(lambda ctx: ctx.is_ota)(
        align(
            lambda ctx: 0x40 if ctx.header.next_offset == 0xFFFFFFFF else 0x4000,
            pattern=b"\x87",
        )
    )


# noinspection PyMethodParameters,PyAttributeOutsideInit
@dataclass
class Flash(DataStruct):
    def update(ctx: Context):
        flash: "Flash" = ctx.self
        # set next_offset to 0 for all images but the last,
        # to allow calculation by Image.update()
        for image in flash.firmware:
            image.header.idx_pkey = 0
            image.header.next_offset = 0
        flash.firmware[-1].header.next_offset = 0xFFFFFFFF

    def update_offsets(ctx: Context):
        flash: "Flash" = ctx.self
        ptable: PartitionTable = flash.ptable.data
        ctx.boot_offset = ptable.partitions[0].offset
        idx_fw1 = ptable.idx_fw1
        ctx.firmware_offset = ptable.partitions[idx_fw1].offset
        if ptable.partitions[idx_fw1].hash_key_valid:
            ctx.firmware_hash_key = ptable.partitions[idx_fw1].hash_key
        else:
            ctx.firmware_hash_key = None

    _0: ... = action(packing(update))
    calibration: bytes = field("16s", default=FLASH_CALIBRATION)

    _1: ... = alignto(0x20)
    ptable: Image = subfield(
        hash_key=lambda ctx: ctx.hash_key,
        is_ota=False,
        is_first=True,
    )
    _2: ... = action(update_offsets)

    _3: ... = alignto(0x1000)
    system: SystemData = subfield()

    _4: ... = alignto(lambda ctx: ctx.boot_offset)
    boot: Image = subfield(
        hash_key=lambda ctx: ctx.hash_key,
        is_ota=False,
        is_first=True,
    )

    _5: ... = alignto(lambda ctx: ctx.firmware_offset)
    _sum32: ... = checksum_start(
        init=lambda ctx: 0,
        update=lambda data, obj, ctx: obj + sum(data),
        end=lambda obj, ctx: obj & 0xFFFFFFFF,
    )
    firmware: List[Image] = repeat(last=header_is_last)(
        subfield(
            hash_key=lambda ctx: ctx.firmware_hash_key,
            is_ota=True,
            is_first=lambda ctx: ctx.G.tell() == ctx.firmware_offset,
        )
    )
    _6: ... = checksum_end(_sum32)
    sum32: int = checksum_field("FW1 sum32")(field("I", default=0xFFFFFFFF))

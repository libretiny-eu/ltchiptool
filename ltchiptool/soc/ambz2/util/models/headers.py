#  Copyright (c) Kuba Szczodrzyński 2023-1-4.

from dataclasses import dataclass
from enum import IntFlag
from typing import List

from datastruct import Context, DataStruct, datastruct, sizeof
from datastruct.fields import adapter, built, field, padding, repeat

from .enums import EncAlgo, HashAlgo, ImageType, SectionType
from .utils import FF_16, FF_32, BitFlag


def header_is_last(ctx: Context) -> bool:
    header: SectionHeader = ctx.P.item.header
    return header.next_offset == 0xFFFFFFFF


@dataclass
class Keyblock(DataStruct):
    decryption: bytes = field("32s", default=FF_32)
    hash: bytes = field("32s", default=FF_32)


@dataclass
class KeyblockOTA(DataStruct):
    decryption: bytes = field("32s", default=FF_32)
    reserved: List[bytes] = repeat(5)(field("32s", default=FF_32))


@dataclass
class ImageHeader(DataStruct):
    class Flags(IntFlag):
        HAS_KEY1 = 1 << 0
        HAS_KEY2 = 1 << 1

    length: int = built("I", lambda ctx: sizeof(ctx._.data))
    next_offset: int = field("I", default=0xFFFFFFFF)
    type: ImageType = field("B")
    is_encrypted: bool = field("?", default=False)
    idx_pkey: int = field("B", default=0xFF)
    flags: Flags = built(
        "B",
        lambda ctx: ImageHeader.Flags(
            int(ctx.user_keys[0] != FF_32) + 2 * int(ctx.user_keys[1] != FF_32)
        ),
    )
    _1: ... = padding(8)
    serial: int = field("I", default=0)
    _2: ... = padding(8)
    user_keys: List[bytes] = repeat(2)(field("32s", default=FF_32))


@dataclass
class SectionHeader(DataStruct):
    length: int = built("I", lambda ctx: sizeof(ctx._.entry) + sizeof(ctx._.data))
    next_offset: int = field("I", default=0xFFFFFFFF)
    type: SectionType = field("B")
    sce_enabled: bool = field("?", default=False)
    xip_page_size: int = field("B", default=0)
    xip_block_size: int = field("B", default=0)
    _1: ... = padding(4)
    valid_pattern: bytes = field("8s", default=bytes(range(8)))
    sce_key_iv_valid: bool = adapter(BitFlag())(
        built("B", lambda ctx: ctx.sce_key != FF_16 and ctx.sce_iv != FF_16),
    )
    _2: ... = padding(7)
    sce_key: bytes = field("16s", default=FF_16)
    sce_iv: bytes = field("16s", default=FF_16)
    _3: ... = padding(32)


@dataclass
@datastruct(repeat_fill=True)
class EntryHeader(DataStruct):
    length: int = built("I", lambda ctx: sizeof(ctx._.data))
    address: int = field("I")
    entry_table: List[int] = repeat(6)(field("I", default=0xFFFFFFFF))


@dataclass
class FST(DataStruct):
    class Flags(IntFlag):
        ENC_EN = 1 << 0
        HASH_EN = 2 << 0

    enc_algo: EncAlgo = field("H", default=EncAlgo.AES_CBC)
    hash_algo: HashAlgo = field("H", default=HashAlgo.SHA256)
    part_size: int = field("I", default=0)
    valid_pattern: bytes = field("8s", default=bytes(range(8)))
    _1: ... = padding(4)
    flags: Flags = field("B", default=Flags.HASH_EN)
    cipher_key_iv_valid: bool = adapter(BitFlag())(
        built("B", lambda ctx: ctx.cipher_key != FF_32 and ctx.cipher_iv != FF_16),
    )
    _2: ... = padding(10)
    cipher_key: bytes = field("32s", default=FF_32)
    cipher_iv: bytes = field("16s", default=FF_16)
    _3: ... = padding(16)

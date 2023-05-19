#  Copyright (c) Kuba Szczodrzyński 2023-3-25.

from dataclasses import dataclass
from typing import List

from datastruct import DataStruct, Endianness, datastruct
from datastruct.fields import const, field, padding, subfield, text, varlist


@dataclass
@datastruct(endianness=Endianness.LITTLE, padding_pattern=b"\x00")
class Partition(DataStruct):
    magic_word: int = const(0x45503130)(field("I"))
    name: str = text(lambda ctx: ctx.G.root.name_len or 24)
    flash_name: str = text(lambda ctx: ctx.G.root.name_len or 24)
    offset: int = field("I")
    length: int = field("I")
    _1: ... = padding(4)


@dataclass
class PartitionTable(DataStruct):
    partitions: List[Partition] = varlist(when=lambda ctx: ctx.G.tell() < ctx.length)(
        subfield()
    )

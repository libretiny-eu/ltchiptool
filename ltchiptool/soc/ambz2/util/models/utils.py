#  Copyright (c) Kuba Szczodrzyński 2023-1-4.

from typing import Callable, Iterable, TypeVar

from datastruct import Adapter, Context

FF_48 = b"\xff" * 48
FF_32 = b"\xff" * 32
FF_16 = b"\xff" * 16

T = TypeVar("T")


def index(func: Callable[[T], int], iterable: Iterable[T], default: T = None) -> T:
    for idx, item in enumerate(iterable):
        if func(item):
            return idx
    return default


class BitFlag(Adapter):
    def encode(self, value: bool, ctx: Context) -> int:
        return 0xFF if value else 0xFE

    def decode(self, value: int, ctx: Context) -> bool:
        return value & 1 == 1

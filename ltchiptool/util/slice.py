# Copyright (c) Kuba Szczodrzyński 2022-06-02.

from typing import Tuple, Union

SliceLike = Union[slice, str, int]


def slice2int(val: SliceLike) -> Tuple[int, int]:
    """Convert a slice-like value (slice, string '7:0' or '3', int '3')
    to a tuple of (start, stop)."""
    if isinstance(val, int):
        return val, val
    if isinstance(val, slice):
        if val.step:
            raise ValueError("value must be a slice without step")
        if val.start < val.stop:
            raise ValueError("start must not be less than stop")
        return val.start, val.stop
    if isinstance(val, str):
        if ":" in val:
            val = val.split(":")
            if len(val) == 2:
                return int(val[0]), int(val[1])
        elif val.isnumeric():
            return int(val), int(val)
    raise ValueError(f"invalid slice format: {val}")

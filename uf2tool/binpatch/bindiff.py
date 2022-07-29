# Copyright (c) Kuba Szczodrzyński 2022-05-27.

from typing import Dict, Tuple


def bindiff(
    data1: bytes, data2: bytes, width: int = 1, single: bool = False
) -> Dict[int, Tuple[bytes, bytes]]:
    out: Dict[int, Tuple[bytes, bytes]] = {}
    offs = -1
    diff1 = b""
    diff2 = b""
    for i in range(0, len(data1), width):
        block1 = data1[i : i + width]
        block2 = data2[i : i + width]
        if block1 == block2:
            # blocks are equal again
            if offs != -1:
                # store and reset current difference
                out[offs] = (diff1, diff2)
                offs = -1
                diff1 = b""
                diff2 = b""
            continue
        # blocks still differ
        if single:
            # single block per difference, so just store it
            out[i] = (block1, block2)
        else:
            if offs == -1:
                # difference starts here
                offs = i
            diff1 += block1
            diff2 += block2
    return out

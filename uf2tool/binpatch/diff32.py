# Copyright (c) Kuba Szczodrzyński 2022-05-27.

from typing import Dict, List

from ltchiptool.util.intbin import intto8, inttole32, letoint, letosint, sinttole32
from uf2tool.models.enums import Opcode

from .bindiff import bindiff


def diff32_write(block1: bytes, block2: bytes) -> bytes:
    # compare blocks:
    # - in 4 byte (32 bit) chunks
    # - report a single chunk in each difference
    diffs = bindiff(block1, block2, width=4, single=True)
    binpatch: Dict[int, List[int]] = {}

    # gather all repeating differences (i.e. memory offsets for OTA1/OTA2)
    for offs, diff in diffs.items():
        (diff1, diff2) = diff
        diff1 = letoint(diff1)
        diff2 = letoint(diff2)
        diff = diff2 - diff1
        if diff in binpatch:
            # difference already in this binpatch, add the offset
            binpatch[diff].append(offs)
        else:
            # a new difference value
            binpatch[diff] = [offs]
        # print(f"Block at 0x{bladdr:x}+{offs:02x} -> {diff1:08x} - {diff2:08x} = {diff2-diff1:x}")
    # print(f"Block at 0x{bladdr:x}: {len(binpatch)} difference(s) at {sum(len(v) for v in binpatch.values())} offsets")

    # write binary patches
    out = b""
    for diff, offs in binpatch.items():
        out += intto8(Opcode.DIFF32.value)
        out += intto8(len(offs) + 4)
        out += sinttole32(diff)
        out += bytes(offs)
    return out


def diff32_apply(data: bytearray, patch: bytes) -> bytearray:
    diff = letosint(patch[0:4])
    for offs in patch[4:]:
        value = letoint(data[offs : offs + 4])
        value += diff
        data[offs : offs + 4] = inttole32(value)
    return data

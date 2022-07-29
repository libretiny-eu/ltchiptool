# Copyright (c) Kuba Szczodrzyński 2022-06-02.

from io import BytesIO

from uf2tool.models.enums import Opcode

from .diff32 import diff32_apply


def binpatch_apply(data: bytearray, binpatch: bytes) -> bytearray:
    io = BytesIO(binpatch)
    while io.tell() < len(binpatch):
        opcode = io.read(1)[0]
        length = io.read(1)[0]
        patch = io.read(length)
        if opcode == Opcode.DIFF32:
            data = diff32_apply(data, patch)
    return data

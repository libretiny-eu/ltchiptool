# Copyright (c) Kuba Szczodrzyński 2022-06-10.

from io import FileIO
from typing import Union

from ltchiptool.util import CRC16, BitInt
from ltchiptool.util.intbin import (
    ByteGenerator,
    ByteSource,
    align_up,
    betoint,
    biniter,
    fileiter,
    geniter,
    inttobe16,
    inttole32,
    letoint,
    pad_up,
)

from .crypto import BekenCrypto
from .models import DataGenerator, DataType
from .rbl import RBL


class BekenBinary:
    crypto: BekenCrypto

    def __init__(self, coeffs: Union[bytes, str] = None) -> None:
        if coeffs:
            if isinstance(coeffs, str):
                coeffs = bytes.fromhex(coeffs)
            if len(coeffs) != 16:
                raise ValueError(
                    f"Invalid length of encryption coefficients: {len(coeffs)}"
                )
            coeffs = list(map(BitInt, map(betoint, biniter(coeffs, 4))))
            self.crypto = BekenCrypto(coeffs)

    def crc(self, data: ByteSource, type: DataType = None) -> DataGenerator:
        for block in geniter(data, 32):
            crc = CRC16.CMS.calc(block)
            block += inttobe16(crc)
            if type:
                yield type, block
            else:
                yield block

    def uncrc(self, data: ByteSource, check: bool = True) -> ByteGenerator:
        for block in geniter(data, 34):
            if check:
                crc = CRC16.CMS.calc(block[0:32])
                crc_found = betoint(block[32:34])
                if crc != crc_found:
                    print(f"CRC invalid: expected={crc:X}, found={crc_found:X}")
                    return
            yield block[0:32]

    def crypt(self, addr: int, data: ByteSource) -> ByteGenerator:
        for word in geniter(data, 4):
            word = letoint(word)
            word = self.crypto.encrypt_u32(addr, word)
            word = inttole32(word)
            yield word
            addr += 4

    def package(
        self,
        f: FileIO,
        addr: int,
        size: int,
        rbl: RBL,
        partial: bool = False,
    ) -> DataGenerator:
        if not rbl.container_size:
            raise ValueError("RBL must have a total size when packaging")
        crc_total = 0

        # yield all data as (type, bytes) tuples, if partial mode enabled
        type_binary = DataType.BINARY if partial else None
        type_padding = DataType.PADDING_SIZE if partial else None
        type_rbl = DataType.RBL if partial else None

        # when to stop reading input data
        data_end = size
        if rbl.has_part_table:
            data_end = size - 0xC0  # do not encrypt the partition table

        # set RBL size including one 16-byte padding
        rbl.raw_size = align_up(size + 16, 32) + 16

        # encrypt the input file, padded to 32 bytes
        data_crypt_gen = self.crypt(
            addr, fileiter(f, size=32, padding=0xFF, count=data_end)
        )
        # iterate over encrypted 32-byte blocks
        for block in geniter(data_crypt_gen, 32):
            # add CRC16 and yield
            yield from self.crc(block, type_binary)
            crc_total += 2
            rbl.update(block)

        # temporary buffer for small-size operations
        buf = b"\xff" * 16  # add 16 bytes of padding

        if rbl.has_part_table:
            # add an unencrypted partition table
            buf += f.read(0xC0)

        # update RBL
        rbl.update(buf)
        # add last padding with different values
        rbl.update(b"\x10" * 16)

        # add last padding with normal values
        buf += b"\xff" * 16
        # yield the temporary buffer
        yield from self.crc(buf, type_binary)
        crc_total += 2 * (len(buf) // 32)

        # pad the entire container with 0xFF, excluding RBL and its CRC16
        pad_size = pad_up(rbl.data_size + crc_total, rbl.container_size_crc) - 102
        if type_padding:
            yield type_padding, pad_size
        else:
            for _ in range(pad_size):
                yield b"\xff"

        # yield RBL with CRC16
        yield from self.crc(rbl.serialize(), type_rbl)

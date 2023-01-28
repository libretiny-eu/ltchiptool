# Copyright (c) Kuba Szczodrzyński 2022-06-10.

import gzip
from binascii import crc32
from typing import IO, Union

from ltchiptool.util.bitint import BitInt
from ltchiptool.util.crc16 import CRC16
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
from .models import DataGenerator, DataType, OTACompression, OTAEncryption
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
            if len(block) < 32:
                block += b"\xFF" * (32 - len(block))
            crc = CRC16.CMS.calc(block)
            block += inttobe16(crc)
            if type:
                yield type, block
            else:
                yield block

    def uncrc(self, data: ByteSource, check: bool = True) -> ByteGenerator:
        for block in geniter(data, 34):
            if check and block != b"\xFF" * 34:
                crc = CRC16.CMS.calc(block[0:32])
                crc_found = betoint(block[32:34])
                if crc != crc_found:
                    raise ValueError(
                        f"CRC invalid: expected={crc:X}, found={crc_found:X}"
                    )
            yield block[0:32]

    def crypt(
        self,
        addr: int,
        data: ByteSource,
        skip_ff: bool = False,
    ) -> ByteGenerator:
        for word in geniter(data, 4):
            word = letoint(word)
            if word != 0xFFFFFFFF or not skip_ff:
                word = self.crypto.encrypt_u32(addr, word)
            word = inttole32(word)
            yield word
            addr += 4

    def package(
        self,
        f: IO[bytes],
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

    @staticmethod
    def _make_aes(key: bytes, iv: bytes):
        try:
            from Cryptodome.Cipher import AES
        except (ImportError, ModuleNotFoundError):
            raise ImportError(
                "PyCryptodomex is required for OTA encryption/decryption. "
                "Install ltchiptool with 'crypto' extras: "
                "pip install ltchiptool[crypto]",
            )
        return AES.new(key=key, mode=AES.MODE_CBC, iv=iv)

    def ota_package(
        self,
        f: IO[bytes],
        rbl: RBL,
        key: Union[bytes, str] = None,
        iv: Union[bytes, str] = None,
    ) -> ByteGenerator:
        if rbl.encryption == OTAEncryption.AES256 and not (key and iv):
            raise ValueError("Encryption without keys requested")
        if isinstance(key, str):
            key = key.encode("utf-8")
        if isinstance(iv, str):
            iv = iv.encode("utf-8")
        data = f.read()

        # calculate FNV1A hash using raw firmware data
        rbl.raw_size = len(data)
        rbl.update(data)

        if rbl.compression == OTACompression.GZIP:
            data = gzip.compress(data, compresslevel=9)
        elif rbl.compression != OTACompression.NONE:
            raise ValueError("Unsupported compression algorithm")

        if rbl.encryption == OTAEncryption.AES256:
            padding = pad_up(len(data), 16)
            data += bytes([padding] * padding)
            aes = self._make_aes(key=key, iv=iv)
            data = aes.encrypt(data)
        elif rbl.encryption != OTAEncryption.NONE:
            raise ValueError("Unsupported encryption algorithm")

        # calculate CRC using compressed & encrypted firmware data
        rbl.data_size = len(data)
        rbl.data_crc = crc32(data)
        yield rbl.serialize()
        yield data

    def ota_unpackage(
        self,
        f: IO[bytes],
        rbl: RBL,
        key: Union[bytes, str] = None,
        iv: Union[bytes, str] = None,
    ) -> ByteGenerator:
        if rbl.encryption == OTAEncryption.AES256 and not (key and iv):
            raise ValueError("Decryption without keys requested")
        if isinstance(key, str):
            key = key.encode("utf-8")
        if isinstance(iv, str):
            iv = iv.encode("utf-8")
        data = f.read()

        if rbl.encryption == OTAEncryption.AES256:
            aes = self._make_aes(key=key, iv=iv)
            data = aes.decrypt(data)
            # trim AES padding
            padding_bytes = data[-1:]
            padding_size = padding_bytes[0]
            if padding_size and padding_bytes * padding_size == data[-padding_size:]:
                data = data[0:-padding_size]
        elif rbl.encryption != OTAEncryption.NONE:
            raise ValueError("Unsupported encryption algorithm")

        if rbl.compression == OTACompression.GZIP:
            data = gzip.decompress(data)
        elif rbl.compression != OTACompression.NONE:
            raise ValueError("Unsupported compression algorithm")

        yield data

# Copyright (c) Kuba Szczodrzyński 2022-06-10.

from binascii import crc32
from dataclasses import dataclass, field
from struct import Struct
from time import time
from typing import Union

from ltchiptool.util.intbin import inttole32, letoint, pad_data

from .models import OTACompression, OTAEncryption


@dataclass
class RBL:
    encryption: OTAEncryption = OTAEncryption.NONE
    compression: OTACompression = OTACompression.NONE
    timestamp: float = field(default_factory=time)
    name: Union[str, bytes] = "app"
    version: Union[str, bytes] = "1.00"
    sn: Union[str, bytes] = "0" * 23
    data_crc: int = 0
    data_hash: int = 0x811C9DC5  # https://github.com/znerol/py-fnvhash/blob/master/fnvhash/__init__.py
    raw_size: int = 0
    data_size: int = 0
    container_size: int = 0
    has_part_table: bool = False

    @property
    def container_size_crc(self) -> int:
        return int(self.container_size + (self.container_size // 32) * 2)

    def update(self, data: bytes):
        self.data_crc = crc32(data, self.data_crc)
        for byte in data:
            if self.data_size < self.raw_size:
                self.data_hash ^= byte
                self.data_hash *= 0x01000193
                self.data_hash %= 0x100000000
            self.data_size += 1

    def serialize(self) -> bytes:
        if isinstance(self.name, str):
            self.name = self.name.encode()
        if isinstance(self.version, str):
            self.version = self.version.encode()
        if isinstance(self.sn, str):
            self.sn = self.sn.encode()
        # based on https://github.com/khalednassar/bk7231tools/blob/main/bk7231tools/analysis/rbl.py
        struct = Struct("<4sbbxxI16s24s24sIIII")  # without header CRC
        rbl = struct.pack(
            b"RBL\x00",
            self.encryption,
            self.compression,
            int(self.timestamp),
            pad_data(self.name, 16, 0x00),
            pad_data(self.version, 24, 0x00),
            pad_data(self.sn, 24, 0x00),
            self.data_crc,
            self.data_hash,
            self.raw_size,
            self.data_size,
        )
        return rbl + inttole32(crc32(rbl))

    @classmethod
    def deserialize(cls, data: bytes) -> "RBL":
        crc_found = letoint(data[-4:])
        data = data[:-4]
        crc_expected = crc32(data)
        if crc_expected != crc_found:
            raise ValueError(
                f"Invalid RBL CRC (expected {crc_expected:X}, found {crc_found:X})"
            )
        struct = Struct("<bbxxI16s24s24sIIII")  # without magic and header CRC
        rbl = cls(*struct.unpack(data[4:]))
        rbl.encryption = OTAEncryption(rbl.encryption)
        rbl.compression = OTACompression(rbl.compression)
        rbl.name = rbl.name.partition(b"\x00")[0].decode()
        rbl.version = rbl.version.partition(b"\x00")[0].decode()
        rbl.sn = rbl.sn.partition(b"\x00")[0].decode()
        return rbl

#  Copyright (c) Kuba Szczodrzyński 2022-12-28.

from __future__ import annotations

import io
from abc import ABC
from dataclasses import dataclass
from enum import IntEnum
from typing import IO, Generator, Optional, Protocol

from Cryptodome.Hash import HMAC, SHA256

from ltchiptool import SocInterface
from ltchiptool.soc.ambz2.binary import MARKER_UNSIGNED
from ltchiptool.util.flash import FlashConnection, ProgressCallback
from ltchiptool.util.intbin import gen2bytes
from uf2tool import UploadContext

from .util.ambz2tool import AmbZ2Tool


class PartitionType(IntEnum):
    PARTAB = 0
    BOOT = 1
    SYS = 2
    CAL = 3
    USER = 4
    FW1 = 5
    FW2 = 6
    VAR = 7
    MP = 8
    RDP = 9
    UNKNOWN = 10


@dataclass(frozen=True)
class PartitionRecord:
    offset: int
    length: int
    type: PartitionType
    dbg_skip: bool
    hash_key: bytes | None

    @classmethod
    def parse(cls, b: bytes) -> PartitionRecord:
        offset = int.from_bytes(b[0:4], "little")
        length = int.from_bytes(b[4:8], "little")
        type = PartitionType(b[8])
        dbg_skip = b[9] != 0
        hash_key = None
        if b[16] & 1:
            # hash key valid
            hash_key = b[32:64]
        return cls(
            offset=offset,
            length=length,
            type=type,
            dbg_skip=dbg_skip,
            hash_key=hash_key,
        )


PTABLE_PATTERN = bytes.fromhex("999996963FCC66FCC033CC03E5DC3162") + b"\xff" * 16
PTABLE_SIZE = 32 + 32 + 32 + 96 + 32 + 64 * 3
PTABLE_OFF_HDR = 0x20 * 7
PTABLE_OFF_SERIAL = PTABLE_OFF_HDR + 0x14
FLASH_BASE = 0x9800_0000


def parse_ptable(b: bytes) -> tuple[PartitionRecord, PartitionRecord]:
    if not b.startswith(PTABLE_PATTERN):
        raise RuntimeError("could not parse partition table: invalid magic")

    o_hdr = 32 + 32 + 32
    part_type = PartitionType(b[o_hdr + 8])
    if part_type != PartitionType.PARTAB:
        raise RuntimeError(
            f"could not parse partition table: invalid header type {part_type}"
        )

    if b[o_hdr + 9]:
        raise RuntimeError("could not parse partition table: encrypted")

    o_payload = o_hdr + 96
    num_imgs = b[o_payload + 4]

    if num_imgs != 2:
        raise RuntimeError(
            f"could not parse partition table: image count {num_imgs} != 2"
        )

    fw_indexes = (b[o_payload + 5], b[o_payload + 6])
    o_records = o_payload + 32

    return tuple(
        PartitionRecord.parse(b[o_records + i * 64 : o_records + i * 64 + 64])
        for i in fw_indexes
    )


class Hasher(Protocol):
    def update(self, msg: bytes):
        ...

    def digest(self) -> bytes:
        ...


def select_partition(amb: AmbZ2Tool) -> tuple[int, bytes, Hasher, int]:
    # read and verify PTABLE
    ptable_raw = gen2bytes(amb.memory_read(0, PTABLE_SIZE, use_flash=True))
    ptable = parse_ptable(ptable_raw)

    # read partition serial numbers
    serials = tuple(
        next(amb.dump_words(FLASH_BASE + p.offset + PTABLE_OFF_SERIAL, 1))[0]
        for p in ptable
    )

    # select partitions based on their serial number
    if serials[1] > serials[0]:
        current_index = 1
        write_index = 0
    else:
        current_index = 0
        write_index = 1
    next_serial = serials[current_index] + 1
    write_partition = ptable[write_index]
    hash_key = write_partition.hash_key
    flash_offset = write_partition.offset

    hasher: Hasher
    if hash_key:
        hasher = HMAC.new(hash_key, digestmod=SHA256)
    else:
        hasher = SHA256.new()

    return write_index + 1, next_serial.to_bytes(4, "little"), hasher, flash_offset


class AmebaZ2Flash(SocInterface, ABC):
    amb: Optional[AmbZ2Tool] = None

    def flash_set_connection(self, connection: FlashConnection) -> None:
        if self.conn:
            self.flash_disconnect()
        self.conn = connection
        self.conn.fill_baudrate(115200)

    def flash_build_protocol(self, force: bool = False) -> None:
        if not force and self.amb:
            return
        self.flash_disconnect()
        self.amb = AmbZ2Tool(
            port=self.conn.port,
            baudrate=self.conn.link_baudrate,
        )
        self.flash_change_timeout(self.conn.timeout, self.conn.link_timeout)

    def flash_change_timeout(self, timeout: float = 0.0, link_timeout: float = 0.0):
        self.flash_build_protocol()
        if timeout:
            self.amb.read_timeout = timeout
            self.conn.timeout = timeout
        if link_timeout:
            self.amb.link_timeout = link_timeout
            self.conn.link_timeout = link_timeout

    def flash_connect(self) -> None:
        if self.amb and self.conn.linked:
            return
        self.flash_build_protocol()
        assert self.amb
        self.amb.link()
        self.amb.change_baudrate(self.conn.baudrate)
        self.conn.linked = True

    def flash_disconnect(self) -> None:
        if self.amb:
            self.amb.close()
        self.amb = None
        self.conn.linked = False

    def flash_get_chip_info_string(self) -> str:
        self.flash_connect()
        assert self.amb
        self.amb.flash_init(configure=False)
        reg = self.amb.register_read(0x4000_01F0)
        vid = (reg >> 8) & 0xF
        ver = (reg >> 4) & 0xF
        rom_ver = "2.1" if ver <= 2 else "3.0"
        items = [
            self.amb.flash_mode.name.replace("_", "/"),
            f"Chip VID: {vid}",
            f"Version: {ver}",
            f"ROM: v{rom_ver}",
        ]
        return " / ".join(items)

    def flash_get_size(self) -> int:
        return 0x200000

    def flash_get_rom_size(self) -> int:
        return 384 * 1024

    def flash_read_raw(
        self,
        offset: int,
        length: int,
        verify: bool = True,
        use_rom: bool = False,
        callback: ProgressCallback = ProgressCallback(),
    ) -> Generator[bytes, None, None]:
        self.flash_connect()
        assert self.amb
        gen = self.amb.memory_read(
            offset=offset,
            length=length,
            use_flash=not use_rom,
            hash_check=verify,
            yield_size=1024,
        )
        yield from callback.update_with(gen)

    def flash_write_raw(
        self,
        offset: int,
        length: int,
        data: IO[bytes],
        verify: bool = True,
        callback: ProgressCallback = ProgressCallback(),
    ) -> None:
        callback.on_message("connecting...")
        self.flash_connect()
        assert self.amb

        callback.on_message("reading partition table...")
        ota_idx, next_serial, hasher, flash_offset = select_partition(self.amb)

        callback.on_message(f"OTA {ota_idx}")
        with io.BytesIO(data.read(length)) as stream:
            callback.on_message("updating serial number and OTA signature...")

            with stream.getbuffer() as buf:
                if buf[0:32] == MARKER_UNSIGNED:
                    # update serial number
                    buf[PTABLE_OFF_SERIAL : PTABLE_OFF_SERIAL + 4] = next_serial

                    # update hash
                    hasher.update(buf[PTABLE_OFF_HDR : PTABLE_OFF_HDR + 0x60])
                    buf[0:32] = hasher.digest()

            callback.on_message(f"OTA {ota_idx} ({flash_offset + offset:#X})")
            # write to flash
            callback.attach(data)
            self.amb.memory_write(
                flash_offset + offset,
                stream,
                use_flash=True,
                hash_check=verify,
            )
            callback.detach(data)

    def flash_write_uf2(
        self,
        ctx: UploadContext,
        verify: bool = True,
        callback: ProgressCallback = ProgressCallback(),
    ) -> None:
        # collect continuous blocks of data
        parts = ctx.collect()
        callback.on_total(sum(len(part.getvalue()) for part in parts.values()) + 4)

        for offset, data in parts.items():
            length = len(data.getvalue())
            data.seek(0)
            self.flash_write_raw(offset, length, data, verify, callback)

        callback.on_message("Booting firmware")
        self.amb.disconnect()
        callback.on_update(4)

# Copyright (c) Kuba Szczodrzyński 2022-07-29.

from abc import ABC
from io import FileIO
from struct import unpack
from typing import BinaryIO, Generator, Optional, Tuple

from ltchiptool import SocInterface
from ltchiptool.util import graph, peek
from ltchiptool.util.intbin import gen2bytes, letoint
from uf2tool import UploadContext

from .util.rtltool import RTL_ROM_BAUD, RTLXMD


def check_xip_binary(
    data: bytes,
    header: bytes = b"81958711",
) -> Optional[Tuple[int, int, bytes]]:
    if data[0:8] != header:
        return None
    if data[16:32] != b"\xFF" * 16:
        return None
    length, start = unpack("<II", data[8:16])
    return start, length, data[32:]


def check_bootloader_binary(data: bytes) -> Optional[Tuple[int, int, bytes]]:
    return check_xip_binary(data, header=b"\x99\x99\x96\x96\x3F\xCC\x66\xFC")


class AmebaZFlash(SocInterface, ABC):
    rtl: RTLXMD = None
    baud: int = RTL_ROM_BAUD

    def _build_protocol(self):
        if self.rtl is not None:
            return
        self.print_protocol()
        self.rtl = RTLXMD(
            port=self.port,
            baud=self.baud,
            timeout=self.link_timeout,
        )
        if not self.rtl.connect():
            raise ValueError(f"Failed to connect on port {self.port}")

    def flash_get_size(self) -> int:
        return 0x200000

    def flash_get_file_type(
        self,
        file: FileIO,
        length: int,
    ) -> Optional[Tuple[str, Optional[int], int, int]]:

        data = peek(file, size=64)
        if not data:
            return None

        if data[0x08:0x0E] == b"RTKWin" or data[0x28:0x2E] == b"RTKWin":
            return "Realtek AmebaZ RAM Image", None, 0, 0

        # stage 0 - check XIP file
        tpl = check_xip_binary(data)
        if tpl:
            start, xip_length, data = tpl
            start = start or None
            type = "SDK" if data.startswith(b"Customer") else "LT"
            if start:
                if start & 0x8000020 != 0x8000020:
                    return "Realtek AmebaZ Unknown Image", None, 0, 0
                ota_idx = 1 if start == 0xB000 else 2
                return f"Realtek AmebaZ {type}-XIP{ota_idx}", start, 0, xip_length
            return f"Realtek AmebaZ {type}-XIP Unknown", None, 0, 0

        # stage 1 - check full dump file
        tpl = check_bootloader_binary(data)
        if not tpl:
            # no bootloader at 0x0, nothing to do
            return None
        start, xip_length, _ = tpl
        if start != 0x8000020:
            # make sure the bootloader offset is correct
            return None
        # read app header
        data = peek(file, size=64, seek=0xB000)
        if not data:
            # bootloader only binary
            if xip_length >= 0x4000:
                # too long, probably not AmebaZ
                return None
            return "Realtek AmebaZ Bootloader", 0, 0, xip_length
        # check XIP at 0xB000
        tpl = check_xip_binary(data)
        if not tpl:
            return None

        if length != 2048 * 1024:
            return "Realtek AmebaZ Incomplete Dump", None, 0, 0
        return "Realtek AmebaZ Full Dump", 0, 0, 0

    def flash_read_raw(
        self,
        start: int,
        length: int,
        verify: bool = True,
        use_rom: bool = False,
    ) -> Generator[bytes, None, None]:
        self._build_protocol()
        success = yield from self.rtl.ReadBlockFlashGenerator(start, length)
        if not success:
            raise ValueError(f"Failed to read from 0x{start:X}")

    def flash_write_raw(
        self,
        start: int,
        length: int,
        data: BinaryIO,
        verify: bool = True,
    ):
        self._build_protocol()
        start |= 0x8000000
        if not self.rtl.WriteBlockFlash(data, start, length):
            raise ValueError(f"Failed to write to 0x{start:X}")
        return data.tell()

    def flash_write_uf2(
        self,
        ctx: UploadContext,
    ):
        # read system data to get active OTA index
        system = gen2bytes(self.flash_read_raw(0x9000, 256))
        if len(system) != 256:
            raise ValueError(
                f"Length invalid while reading from 0x9000 - {len(system)}"
            )
        # read OTA switch value
        ota_switch = bin(letoint(system[4:8]))[2:]
        # count 0-bits
        ota_idx = 1 + (ota_switch.count("0") % 2)
        # validate OTA2 address in system data
        if ota_idx == 2:
            ota2_addr = letoint(system[0:4]) & 0xFFFFFF
            part_addr = ctx.get_offset("ota2", 0)
            if ota2_addr != part_addr:
                raise ValueError(
                    f"Invalid OTA2 address on chip - found {ota2_addr}, expected {part_addr}"
                )

        graph(2, f"Flashing image to OTA {ota_idx}...")
        # collect continuous blocks of data
        parts = ctx.collect(ota_idx=ota_idx)
        # write blocks to flash
        for offset, data in parts.items():
            length = len(data.getvalue())
            data.seek(0)
            graph(2, f"Writing {length} bytes to 0x{offset:06x}")
            self.flash_write_raw(offset, length, data)
        return True

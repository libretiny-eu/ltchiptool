# Copyright (c) Kuba Szczodrzyński 2022-07-29.

from abc import ABC
from typing import BinaryIO, Generator

from ltchiptool import SocInterface
from ltchiptool.util import graph
from ltchiptool.util.intbin import gen2bytes, letoint
from uf2tool import UploadContext

from .util.rtltool import RTL_ROM_BAUD, RTLXMD


class AmebaZFlash(SocInterface, ABC):
    rtl: RTLXMD = None
    baud: int = RTL_ROM_BAUD

    def build_protocol(self):
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

    def flash_read_raw(
        self,
        offset: int,
        length: int,
        use_rom: bool = False,
    ) -> Generator[bytes, None, None]:
        self.build_protocol()
        success = yield from self.rtl.ReadBlockFlashGenerator(offset, length)
        if not success:
            raise ValueError(f"Failed to read from 0x{offset:X}")

    def flash_write_raw(
        self,
        offset: int,
        length: int,
        data: BinaryIO,
        verify: bool = True,
    ):
        self.build_protocol()
        offset |= 0x8000000
        if not self.rtl.WriteBlockFlash(data, offset, length):
            raise ValueError(f"Failed to write to 0x{offset:X}")
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

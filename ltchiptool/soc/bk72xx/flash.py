# Copyright (c) Kuba Szczodrzyński 2022-07-29.

from abc import ABC
from typing import BinaryIO, Generator

from bk7231tools.serial import BK7231Serial

from ltchiptool import SocInterface
from ltchiptool.util import graph
from uf2tool import UploadContext


class BK72XXFlash(SocInterface, ABC):
    bk: BK7231Serial = None

    def build_protocol(self):
        if self.bk is not None:
            return
        self.print_protocol()
        self.bk = BK7231Serial(
            port=self.port,
            baudrate=self.baud,
            link_timeout=self.link_timeout,
            cmnd_timeout=self.read_timeout,
        )

    def flash_read_raw(
        self,
        offset: int,
        length: int,
        use_rom: bool = False,
    ) -> Generator[bytes, None, None]:
        self.build_protocol()
        return self.bk.flash_read(start=offset, length=length)

    def flash_write_raw(
        self,
        offset: int,
        length: int,
        data: BinaryIO,
        verify: bool = True,
    ):
        self.build_protocol()
        if not self.bk.program_flash(
            io=data,
            io_size=length,
            start=offset,
            crc_check=verify,
        ):
            raise ValueError(f"Failed to write to 0x{offset:X}")

    def flash_write_uf2(
        self,
        ctx: UploadContext,
    ):
        # collect continuous blocks of data (before linking, as this takes time)
        parts = ctx.collect(ota_idx=1)

        # connect to chip
        self.build_protocol()

        # write blocks to flash
        for offs, data in parts.items():
            length = len(data.getvalue())
            data.seek(0)
            graph(2, f"Writing {length} bytes to 0x{offs:06x}")
            try:
                self.bk.program_flash(
                    io=data,
                    io_size=length,
                    start=offs,
                    verbose=False,
                    crc_check=True,
                    dry_run=False,
                    really_erase=True,
                )
            except ValueError as e:
                raise RuntimeError(f"Writing failed: {e.args[0]}")
        # reboot the chip
        self.bk.reboot_chip()

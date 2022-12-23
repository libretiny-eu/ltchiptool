# Copyright (c) Kuba Szczodrzyński 2022-07-29.

from abc import ABC
from logging import info

from bk7231tools.serial import BK7231Serial

from ltchiptool import SocInterface
from uf2tool import UploadContext


class BK72XXFlash(SocInterface, ABC):
    def build_protocol(self, baudrate: int):
        return BK7231Serial(
            port=self.port,
            baudrate=baudrate,
            link_timeout=self.link_timeout,
            cmnd_timeout=self.read_timeout,
        )

    def flash_write_uf2(
        self,
        ctx: UploadContext,
    ):
        # collect continuous blocks of data (before linking, as this takes time)
        parts = ctx.collect(ota_idx=1)

        prefix = "|   |--"
        baudrate = self.baud or ctx.baudrate or 115200
        info(f"{prefix} Trying to link on {self.port} @ {baudrate}")
        # connect to chip
        bk = self.build_protocol(baudrate)

        # write blocks to flash
        for offs, data in parts.items():
            length = len(data.getvalue())
            data.seek(0)
            info(f"{prefix} Writing {length} bytes to 0x{offs:06x}")
            try:
                bk.program_flash(
                    data,
                    length,
                    offs,
                    verbose=False,
                    crc_check=True,
                    dry_run=False,
                    really_erase=True,
                )
            except ValueError as e:
                raise RuntimeError(f"Writing failed: {e.args[0]}")
        # reboot the chip
        bk.reboot_chip()

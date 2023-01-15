#  Copyright (c) Kuba Szczodrzyński 2023-1-15.

from logging import debug
from os import SEEK_SET, makedirs, stat
from os.path import dirname
from typing import Callable

import wx

from ltchiptool import SocInterface
from ltchiptool.util.flash import (
    ClickProgressCallback,
    FlashConnection,
    FlashOp,
    format_flash_guide,
)
from ltchiptool.util.logging import LoggingHandler
from ltchiptool.util.misc import sizeof
from uf2tool import UploadContext
from uf2tool.models import UF2

from .base import BaseThread


class FlashThread(BaseThread):
    callback: ClickProgressCallback

    def __init__(
        self,
        port: str,
        baudrate: int | None,
        operation: FlashOp,
        file: str,
        soc: SocInterface,
        offset: int,
        skip: int,
        length: int | None,
        verify: bool,
        uf2: UF2 | None,
        on_chip_info: Callable[[str], None],
    ):
        super().__init__()
        self.port = port
        self.baudrate = baudrate
        self.operation = operation
        self.file = file
        self.soc = soc
        self.offset = offset
        self.skip = skip
        self.length = length
        self.verify = verify
        self.uf2 = uf2
        self.on_chip_info = on_chip_info

    def run_impl(self):
        debug(
            f"Starting {self.operation.name} operation; "
            f"file = {self.file}, "
            f"port = {self.port} @ {self.baudrate or 'Auto'}"
        )
        self.callback = ClickProgressCallback()
        with self.callback:
            try:
                self._link()
                if self.operation == FlashOp.WRITE:
                    self._do_write()
                else:
                    self._do_read()
            except Exception as e:
                print(e)
                if self.should_run():
                    # show exceptions only if not cancelled
                    wx.MessageBox(
                        message=str(e),
                        caption="Error",
                        style=wx.ICON_ERROR,
                    )
        self.soc.flash_disconnect()

    def stop(self):
        super().stop()
        if self.uf2:
            # try to break UF2 flashing
            self.soc.flash_disconnect()

    def _link(self):
        self.soc.flash_set_connection(FlashConnection(self.port, self.baudrate))
        self.soc.flash_change_timeout(link_timeout=0.5)
        elapsed = 0
        while self.should_run():
            match elapsed:
                case 10:
                    # guide the user how to reset the chip
                    for line in format_flash_guide(self.soc):
                        LoggingHandler.get().emit_string("I", line, color="bright_blue")
                case _ if elapsed and elapsed % 4 == 0:
                    # HW-reset every 2.0 seconds
                    self.callback.on_message("Hardware reset...")
                    self.soc.flash_hw_reset()
                case _:
                    self.callback.on_message("Connecting to the chip")

            try:
                debug("Connecting")
                self.soc.flash_disconnect()
                self.soc.flash_connect()
                self.callback.on_message("Connection successful!")
                break
            except TimeoutError:
                elapsed += 1
        if self.should_stop():
            return
        chip_info = self.soc.flash_get_chip_info_string()
        self.on_chip_info(f"Chip info: {chip_info}")

    def _do_write(self):
        if self.should_stop():
            return
        self.callback.on_message(None)

        if self.uf2:
            ctx = UploadContext(self.uf2)
            self.soc.flash_write_uf2(
                ctx=ctx,
                verify=self.verify,
                callback=self.callback,
            )
            return

        file = open(self.file, "rb")
        size = stat(self.file).st_size
        _read = file.read

        def read(n: int = -1) -> bytes | None:
            if self.should_stop():
                return None
            return _read(n)

        file.read = read

        if self.skip + self.length > size:
            raise ValueError(f"File is too small (requested to write too much data)")

        max_length = self.soc.flash_get_size()
        if self.offset > max_length - self.length:
            raise ValueError(
                f"Writing length {sizeof(self.length)} @ 0x{self.offset:X} is more "
                f"than chip capacity ({sizeof(max_length)})",
            )

        file.seek(self.skip, SEEK_SET)
        tell = file.tell()
        debug(f"Starting file position: {tell} / 0x{tell:X} / {sizeof(tell)}")
        self.callback.on_total(self.length)
        self.soc.flash_write_raw(
            offset=self.offset,
            length=self.length,
            data=file,
            verify=self.verify,
            callback=self.callback,
        )

    def _do_read(self):
        if self.should_stop():
            return
        self.callback.on_message(None)

        if self.operation == FlashOp.READ_ROM:
            max_length = self.soc.flash_get_rom_size()
        else:
            max_length = self.soc.flash_get_size()

        self.length = self.length or (max_length - self.offset)

        if self.offset + self.length > max_length:
            raise ValueError(
                f"Reading length {sizeof(self.length)} @ 0x{self.offset:X} is more "
                f"than chip capacity ({sizeof(max_length)})",
            )

        makedirs(dirname(self.file), exist_ok=True)
        file = open(self.file, "wb")
        self.callback.on_total(self.length)
        for chunk in self.soc.flash_read_raw(
            offset=self.offset,
            length=self.length,
            verify=self.verify,
            use_rom=self.operation == FlashOp.READ_ROM,
            callback=self.callback,
        ):
            file.write(chunk)
            if self.should_stop():
                break
        file.close()

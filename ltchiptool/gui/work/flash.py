#  Copyright (c) Kuba Szczodrzyński 2023-1-15.

from logging import debug
from os import SEEK_SET, makedirs, stat
from os.path import dirname
from typing import Callable

from ltchiptool import SocInterface
from ltchiptool.util.flash import (
    FlashConnection,
    FlashMemoryType,
    FlashOp,
    format_flash_guide,
)
from ltchiptool.util.logging import LoggingHandler
from ltchiptool.util.misc import sizeof
from ltchiptool.util.streams import ClickProgressCallback
from uf2tool import UploadContext

from .base import BaseThread

OP_TO_MEMORY = {
    FlashOp.READ: FlashMemoryType.FLASH,
    FlashOp.READ_ROM: FlashMemoryType.ROM,
    FlashOp.READ_EFUSE: FlashMemoryType.EFUSE,
}


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
        ctx: UploadContext | None,
        on_chip_info_summary: Callable[[str], None],
        on_chip_info_full: Callable[[list[tuple[str, str]]], None],
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
        self.ctx = ctx
        self.on_chip_info_summary = on_chip_info_summary
        self.on_chip_info_full = on_chip_info_full

    def run_impl(self):
        debug(
            f"Starting {self.operation.name} operation; "
            f"file = {self.file}, "
            f"port = {self.port} @ {self.baudrate or 'Auto'}"
        )
        self.callback = ClickProgressCallback()
        with self.callback:
            self._link()
            self.callback.on_message("Starting operation...")
            match self.operation:
                case FlashOp.WRITE:
                    self._do_write()
                case FlashOp.READ | FlashOp.READ_ROM | FlashOp.READ_EFUSE:
                    self._do_read()
                case FlashOp.READ_INFO:
                    self._do_info()
        self.soc.flash_disconnect()

    def stop(self):
        super().stop()
        # try to break flashing & cleanup
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
                case _ if elapsed and elapsed % 8 == 0:
                    # HW-reset every 4.0 seconds
                    self.callback.on_message("Hardware reset...")
                    self.soc.flash_hw_reset()
                case _ if elapsed and elapsed % 8 == 4:
                    # SW-reset every 4.0 seconds
                    self.callback.on_message("Software reset...")
                    self.soc.flash_sw_reset()
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
        self.callback.on_message("Reading chip info...")
        chip_info = self.soc.flash_get_chip_info_string()
        self.on_chip_info_summary(f"Chip info: {chip_info}")

    def _do_write(self):
        if self.should_stop():
            return

        if self.ctx:
            self.callback.on_message(None)
            self.soc.flash_write_uf2(
                ctx=self.ctx,
                verify=self.verify,
                callback=self.callback,
            )
            return

        file = open(self.file, "rb")
        file_size = stat(self.file).st_size
        _read = file.read

        def read(n: int = -1) -> bytes | None:
            if self.should_stop():
                return None
            return _read(n)

        file.read = read

        self.length = self.length or max(file_size - self.skip, 0)
        if self.skip + self.length > file_size:
            raise ValueError(f"File is too small (requested to write too much data)")

        self.callback.on_message("Checking flash size...")
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
        self.callback.on_message(None)
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

        memory = OP_TO_MEMORY[self.operation]
        self.callback.on_message(f"Checking {memory.value} size...")
        max_length = self.soc.flash_get_size(memory)

        self.length = self.length or max(max_length - self.offset, 0)

        if self.offset + self.length > max_length:
            raise ValueError(
                f"Reading length {sizeof(self.length)} @ 0x{self.offset:X} is more "
                f"than chip capacity ({sizeof(max_length)})",
            )

        makedirs(dirname(self.file), exist_ok=True)
        file = open(self.file, "wb")
        self.callback.on_total(self.length)
        self.callback.on_message(None)
        for chunk in self.soc.flash_read_raw(
            offset=self.offset,
            length=self.length,
            verify=self.verify,
            memory=memory,
            callback=self.callback,
        ):
            file.write(chunk)
            if self.should_stop():
                break
        file.close()

    def _do_info(self):
        if self.should_stop():
            return

        chip_info = self.soc.flash_get_chip_info()
        self.on_chip_info_full(chip_info)

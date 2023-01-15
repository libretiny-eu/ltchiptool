#  Copyright (c) Kuba Szczodrzyński 2023-1-15.

from logging import debug
from time import sleep

from ltchiptool import SocInterface
from ltchiptool.util.flash import ClickProgressCallback, FlashOp, format_flash_guide
from ltchiptool.util.logging import LoggingHandler

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

    def run_impl(self):
        debug(
            f"Starting {self.operation.name} operation; "
            f"file = {self.file}, "
            f"port = {self.port} @ {self.baudrate or 'Auto'}"
        )
        self.callback = ClickProgressCallback()
        with self.callback:
            self._link()
            if self.should_stop():
                return
            self._transfer()

    def _link(self):
        self.soc.set_uart_params(
            port=self.port,
            baud=self.baudrate,
            read_timeout=0.5,
            link_timeout=0.5,
        )
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
                break
            except TimeoutError:
                elapsed += 1

    def _transfer(self):
        self.callback.on_message(None)
        self.callback.on_total(50)
        for _ in range(50):
            sleep(0.1)
            self.callback.on_update(1)

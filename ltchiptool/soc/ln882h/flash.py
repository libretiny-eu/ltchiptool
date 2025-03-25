# Copyright (c) Etienne Le Cousin 2025-01-02.

from abc import ABC
from typing import IO, Generator, List, Optional, Tuple, Union

from ltchiptool import SocInterface
from ltchiptool.util.flash import FlashConnection, FlashFeatures, FlashMemoryType
from ltchiptool.util.streams import ProgressCallback
from uf2tool import OTAScheme, UploadContext

from .util.ln882htool import LN882hTool

LN882H_GUIDE = [
    "Connect UART1 of the LN882h to the USB-TTL adapter:",
    [
        ("PC", "LN882h"),
        ("RX", "TX1 (GPIOA2 / P2)"),
        ("TX", "RX1 (GPIOA3 / P3)"),
        ("", ""),
        ("GND", "GND"),
    ],
    "Using a good, stable 3.3V power supply is crucial. Most flashing issues\n"
    "are caused by either voltage drops during intensive flash operations,\n"
    "or bad/loose wires.",
    "The UART adapter's 3.3V power regulator is usually not enough. Instead,\n"
    "a regulated bench power supply, or a linear 1117-type regulator is recommended.",
    "To enter download mode, the chip has to be rebooted while the flashing program\n"
    "is trying to establish communication.\n"
    "In order to do that, you need to bridge BOOT pin (GPIOA9) to GND with a wire.",
]


class LN882hFlash(SocInterface, ABC):
    ln882h: Optional[LN882hTool] = None
    info: List[Tuple[str, str]] = None

    def flash_get_features(self) -> FlashFeatures:
        return FlashFeatures()

    def flash_get_guide(self) -> List[Union[str, list]]:
        return LN882H_GUIDE

    def flash_get_docs_url(self) -> Optional[str]:
        return "https://docs.libretiny.eu/link/flashing-ln882h"

    def flash_set_connection(self, connection: FlashConnection) -> None:
        if self.conn:
            self.flash_disconnect()
        self.conn = connection
        self.conn.fill_baudrate(115200)

    def flash_build_protocol(self, force: bool = False) -> None:
        if not force and self.ln882h:
            return
        self.flash_disconnect()
        self.ln882h = LN882hTool(
            port=self.conn.port,
            baudrate=self.conn.link_baudrate,
        )
        self.flash_change_timeout(self.conn.timeout, self.conn.link_timeout)

    def flash_change_timeout(self, timeout: float = 0.0, link_timeout: float = 0.0):
        self.flash_build_protocol()
        if timeout:
            self.ln882h.read_timeout = timeout
            self.conn.timeout = timeout
        if link_timeout:
            self.ln882h.link_timeout = link_timeout
            self.conn.link_timeout = link_timeout

    def flash_connect(self, callback: ProgressCallback = ProgressCallback()) -> None:
        if self.ln882h and self.conn.linked:
            return
        self.flash_build_protocol()
        assert self.ln882h
        self.ln882h.link()

        def cb(i, n, t, sent):
            callback.on_update(sent - cb.total_sent)
            cb.total_sent = sent

        cb.total_sent = 0

        callback.on_message(f"Loading Ram Code")
        self.ln882h.ram_boot(cb)
        self.conn.linked = True

    def flash_disconnect(self) -> None:
        if self.ln882h:
            self.ln882h.close()
        self.ln882h = None
        if self.conn:
            self.conn.linked = False

    def flash_get_chip_info(self) -> List[Tuple[str, str]]:
        if self.info:
            return self.info
        self.flash_connect()
        assert self.ln882h

        flash_info = self.ln882h.command("flash_info")[-1]
        flash_info = dict(s.split(":") for s in flash_info.split(","))

        self.info = [
            ("Flash ID", flash_info["id"]),
            ("Flash Size", flash_info["flash size"]),
            ("Flash UUID", self.ln882h.command("flash_uid")[-1][10:]),
            ("OTP MAC", self.ln882h.command("get_mac_in_flash_otp")[-2]),
        ]
        return self.info

    def flash_get_chip_info_string(self) -> str:
        self.flash_connect()
        assert self.ln882h
        return "LN882H"

    def flash_get_size(self, memory: FlashMemoryType = FlashMemoryType.FLASH) -> int:
        self.flash_connect()
        assert self.ln882h
        if memory == FlashMemoryType.EFUSE:
            raise NotImplementedError("Memory type not readable via UART")
        else:
            # It appears that flash size is coded in the low byte of flash ID as 2^X
            # Ex: LN882HKI id=0xEB6015 --> 0x15 = 21 --> flash_size = 2^21 = 2MB
            flash_info = self.ln882h.command("flash_info")[-1]
            flash_info = dict(s.split(":") for s in flash_info.split(","))
            flash_size = 1 << (int(flash_info["id"], 16) & 0xFF)
            return flash_size

    def flash_read_raw(
        self,
        offset: int,
        length: int,
        verify: bool = True,
        memory: FlashMemoryType = FlashMemoryType.FLASH,
        callback: ProgressCallback = ProgressCallback(),
    ) -> Generator[bytes, None, None]:
        self.flash_connect()
        assert self.ln882h
        if memory == FlashMemoryType.EFUSE:
            raise NotImplementedError("Memory type not readable via UART")
        else:
            gen = self.ln882h.flash_read(
                offset=offset,
                length=length,
                verify=verify,
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
        self.flash_connect()
        assert self.ln882h

        def cb(i, n, t, sent):
            callback.on_update(sent - cb.total_sent)
            cb.total_sent = sent

        cb.total_sent = 0

        self.ln882h.flash_write(
            offset=offset,
            stream=data,
            callback=cb,
        )

    def flash_write_uf2(
        self,
        ctx: UploadContext,
        verify: bool = True,
        callback: ProgressCallback = ProgressCallback(),
    ) -> None:
        # collect continuous blocks of data (before linking, as this takes time)
        parts = ctx.collect_data(OTAScheme.FLASHER_SINGLE)
        callback.on_total(sum(len(part.getvalue()) for part in parts.values()))

        # connect to chip
        self.flash_connect()

        # write blocks to flash
        for offset, data in parts.items():
            length = len(data.getvalue())
            data.seek(0)
            callback.on_message(f"Writing (0x{offset:06X})")
            gen = self.flash_write_raw(
                offset=offset,
                data=data,
                length=length,
                callback=callback,
            )

        callback.on_message("Booting firmware")
        # reboot the chip
        self.ln882h.disconnect()

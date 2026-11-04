# Copyright (c) Bl00d-B0b 2026-08-06.

from abc import ABC
from logging import warning
from os.path import dirname, join
from typing import IO, Generator, List, Optional, Tuple, Union

from ltchiptool import SocInterface
from ltchiptool.util.fileio import readbin
from ltchiptool.util.flash import FlashConnection, FlashFeatures, FlashMemoryType
from ltchiptool.util.misc import sizeof
from ltchiptool.util.streams import ProgressCallback

from .util.ambdtool import AMBD_BLOCK_SIZE, AMBD_ROM_BAUDRATE, AmbDTool

AMEBAD_GUIDE = [
    "Connect the USB-TTL adapter to LOG_UART:",
    [
        ("PC", "RTL8720D"),
        ("RX", "LOG_TX (PA7)"),
        ("TX", "LOG_RX (PA8)"),
        ("", ""),
        ("GND", "GND"),
    ],
    "On the BW16 KIT, the USB-C socket connects to the AT-command UART\n"
    "(PB1/PB2) and can NOT flash the chip - use the LOG_UART pins with an\n"
    "external USB-TTL adapter.",
    "To enter UART download mode:\n"
    " - connect LOG_TX to GND\n"
    " - press/release the reset (CHIP_EN) button\n"
    " - release LOG_TX",
]


class AmebaDFlash(SocInterface, ABC):
    amb: Optional[AmbDTool] = None
    flash_id: Optional[bytes] = None
    loader: Optional[bytes] = None

    def flash_get_features(self) -> FlashFeatures:
        return FlashFeatures(
            can_read_rom=False,
            can_read_efuse=False,
        )

    def flash_get_guide(self) -> List[Union[str, list]]:
        return AMEBAD_GUIDE

    def flash_get_docs_url(self) -> Optional[str]:
        return "https://docs.libretiny.eu/link/flashing-realtek-ambd"

    def flash_set_connection(self, connection: FlashConnection) -> None:
        if self.conn:
            self.flash_disconnect()
        self.conn = connection
        # loader upload always runs at the ROM baudrate; transfers default to
        # 460800 afterwards (bench: ~2.5x faster than 115200, while 921600
        # gains nothing more - the loader-side SPI read dominates)
        self.conn.fill_baudrate(460800, link_baudrate=AMBD_ROM_BAUDRATE)

    def flash_build_protocol(self, force: bool = False) -> None:
        if not force and self.amb:
            return
        self.flash_disconnect()
        self.amb = AmbDTool(
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
        if self.loader is None:
            self.loader = readbin(
                join(dirname(__file__), "stub", "imgtool_flashloader_amebad.bin")
            )
        self.amb.loader_ensure(self.loader)
        if self.conn.baudrate != self.conn.link_baudrate:
            self.amb.change_baudrate(self.conn.baudrate)
        self.flash_id = self.amb.flash_read_id()
        self.conn.linked = True

    def flash_disconnect(self) -> None:
        if self.amb:
            self.amb.close()
        self.amb = None
        if self.conn:
            self.conn.linked = False

    def flash_get_chip_info(self) -> List[Tuple[str, str]]:
        self.flash_connect()
        assert self.flash_id
        return [
            ("Flash ID", self.flash_id.hex(" ").upper()),
            ("Flash Size", sizeof(self.flash_get_size())),
        ]

    def flash_get_chip_info_string(self) -> str:
        self.flash_connect()
        assert self.flash_id
        return f"Flash ID {self.flash_id.hex(' ').upper()}"

    def flash_get_size(self, memory: FlashMemoryType = FlashMemoryType.FLASH) -> int:
        if memory != FlashMemoryType.FLASH:
            raise NotImplementedError("Memory type not readable via UART")
        self.flash_connect()
        assert self.flash_id
        size_id = self.flash_id[2]
        if 0x11 <= size_id <= 0x19:
            return 1 << size_id
        warning(f"Couldn't process flash ID: got {self.flash_id.hex()}")
        return 0x400000

    def flash_read_raw(
        self,
        offset: int,
        length: int,
        verify: bool = True,
        memory: FlashMemoryType = FlashMemoryType.FLASH,
        callback: ProgressCallback = ProgressCallback(),
    ) -> Generator[bytes, None, None]:
        if memory != FlashMemoryType.FLASH:
            raise NotImplementedError("Memory type not readable via UART")
        self.flash_connect()
        assert self.amb
        gen = self.amb.flash_read(
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
        assert self.amb
        block = data.read(length)
        if len(block) != length:
            raise ValueError(f"Data length invalid: {len(block)} != {length}")
        callback.on_total(length)
        last_success = 0

        def xm_callback(_total: int, success: int, _error: int) -> None:
            # xmodem reports cumulative packet counts; each carries 1024 bytes
            nonlocal last_success
            callback.on_update((success - last_success) * 1024)
            last_success = success

        self.amb.flash_write(
            offset=offset,
            data=block,
            verify=verify,
            callback=xm_callback,
        )

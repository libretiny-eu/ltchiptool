#  Copyright (c) Kuba Szczodrzyński 2022-12-28.

from abc import ABC
from typing import Generator, Optional

from ltchiptool import SocInterface
from ltchiptool.util.flash import FlashConnection, ProgressCallback

from .util.ambz2tool import AmbZ2Tool


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
        gen = self.amb.memory_read(
            offset=offset,
            length=length,
            use_flash=not use_rom,
            hash_check=verify,
            yield_size=1024,
        )
        yield from callback.update_with(gen)

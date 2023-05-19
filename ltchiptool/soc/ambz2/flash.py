#  Copyright (c) Kuba Szczodrzyński 2022-12-28.

from abc import ABC
from typing import IO, Generator, Optional

from ltchiptool import SocInterface
from ltchiptool.util.flash import FlashConnection
from ltchiptool.util.streams import ProgressCallback
from uf2tool import OTAScheme, UploadContext

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
        assert self.amb
        self.amb.link()
        self.amb.change_baudrate(self.conn.baudrate)
        self.conn.linked = True

    def flash_disconnect(self) -> None:
        if self.amb:
            self.amb.close()
        self.amb = None
        if self.conn:
            self.conn.linked = False

    def flash_get_chip_info_string(self) -> str:
        self.flash_connect()
        assert self.amb
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
        assert self.amb
        gen = self.amb.memory_read(
            offset=offset,
            length=length,
            use_flash=not use_rom,
            hash_check=verify,
            yield_size=1024,
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
        callback.attach(data, limit=length)
        self.amb.memory_write(
            offset=offset,
            stream=data,
            use_flash=True,
            hash_check=verify,
        )
        callback.detach(data)

    def flash_write_uf2(
        self,
        ctx: UploadContext,
        verify: bool = True,
        callback: ProgressCallback = ProgressCallback(),
    ) -> None:
        # We're always flashing to OTA1/FW1 image.
        # Firmware 'serial' is set to 0xFFFFFFFF at build-time,
        # so that the FW2 image will not be chosen instead of FW1.
        #
        # The flasher (and the on-device OTA code) will try to remove
        # the OTA signature of the 2nd image, so that it doesn't boot anymore.
        # TODO actually remove the signature
        #
        # Recalculating serial numbers would involve recalculating hashes,
        # which is not as simple as writing 32x 0xFF and clearing the bits.
        # In reality, there's not much sense in keeping two FW images anyway.

        # collect continuous blocks of data
        parts = ctx.collect_data(OTAScheme.FLASHER_DUAL_1)
        callback.on_total(sum(len(part.getvalue()) for part in parts.values()) + 4)

        # write blocks to flash
        for offset, data in parts.items():
            length = len(data.getvalue())
            data.seek(0)
            callback.on_message(f"Writing (0x{offset:06X})")
            self.flash_write_raw(offset, length, data, verify, callback)

        callback.on_message("Booting firmware")
        self.amb.disconnect()
        callback.on_update(4)

# Copyright (c) Kuba Szczodrzyński 2022-07-29.

from abc import ABC
from io import BytesIO
from logging import debug, warning
from time import sleep
from typing import IO, Generator, List, Optional, Union

from ltchiptool import SocInterface
from ltchiptool.soc.amb.system import SystemData
from ltchiptool.util.flash import FlashConnection
from ltchiptool.util.intbin import gen2bytes
from ltchiptool.util.logging import verbose
from ltchiptool.util.streams import ProgressCallback
from uf2tool import OTAScheme, UploadContext

from .util.ambzcode import AmbZCode
from .util.ambztool import (
    AMBZ_CHIP_TYPE,
    AMBZ_FLASH_ADDRESS,
    AMBZ_ROM_BAUDRATE,
    AmbZTool,
)

AMEBAZ_GUIDE = [
    "Connect UART2 of the Realtek chip to the USB-TTL adapter:",
    [
        ("PC", "RTL8710B"),
        ("RX", "TX2 (Log_TX / PA30)"),
        ("TX", "RX2 (Log_RX / PA29)"),
        ("RTS", "CEN (or RST, optional)"),
        ("DTR", "TX2 (Log_TX / PA30, optional)"),
        ("", ""),
        ("GND", "GND"),
    ],
    "Make sure to use a good 3.3V power supply, otherwise the adapter might\n"
    "lose power during chip reset. Usually, the adapter's power regulator\n"
    "is not enough and an external power supply is needed (like AMS1117).",
    "If you didn't connect RTS and DTR, you need to put the chip in download\n"
    "mode manually. This is done by connecting CEN to GND, while holding TX2 (Log_TX)\n"
    "to GND as well. After doing that, you need to disconnect TX2 from GND.",
    "If the download mode is enabled, you'll see a few garbage characters\n"
    "printed to the serial console every second.",
]


# noinspection PyProtectedMember
class AmebaZFlash(SocInterface, ABC):
    amb: Optional[AmbZTool] = None
    chip_info: bytes = None

    def flash_set_connection(self, connection: FlashConnection) -> None:
        if self.conn:
            self.flash_disconnect()
        self.conn = connection
        # use 460800 max. as default, since most cheap adapters can't go faster anyway
        self.conn.fill_baudrate(460800, link_baudrate=AMBZ_ROM_BAUDRATE)

    def flash_build_protocol(self, force: bool = False) -> None:
        if not force and self.amb:
            return
        self.flash_disconnect()
        self.amb = AmbZTool(
            port=self.conn.port,
            baudrate=self.conn.link_baudrate,
            read_timeout=0.2,
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

    def flash_sw_reset(self) -> None:
        self.flash_build_protocol()
        port = self.amb.s
        prev_baudrate = port.baudrate
        port.baudrate = 115200
        sleep(0.1)
        # try software reset by writing the family ID, preceded by 55AA
        magic_word = b"\x55\xAA" + self.family.id.to_bytes(length=4, byteorder="big")
        port.write(magic_word)
        sleep(0.5)
        port.baudrate = prev_baudrate

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
            try:
                self.amb.disconnect()
            except TimeoutError:
                pass
            self.amb.close()
        self.amb = None
        if self.conn:
            self.conn.linked = False

    def _read_chip_info(self) -> None:
        self.flash_connect()
        assert self.amb
        self.chip_info = self.amb.ram_boot_read(
            AmbZCode.read_chip_id(offset=0)
            + AmbZCode.read_flash_id(offset=1)
            + AmbZCode.print_data(length=4)
        )
        debug(f"Received chip info: {self.chip_info.hex()}")

    def flash_get_chip_info_string(self) -> str:
        if not self.chip_info:
            self._read_chip_info()
        chip_id = self.chip_info[0]
        return AMBZ_CHIP_TYPE.get(chip_id, f"Unknown 0x{chip_id:02X}")

    def flash_get_guide(self) -> List[Union[str, list]]:
        return AMEBAZ_GUIDE

    def flash_get_size(self) -> int:
        if not self.chip_info:
            self._read_chip_info()
        size_id = self.chip_info[3]
        if 0x14 <= size_id <= 0x19:
            return 1 << size_id
        warning(f"Couldn't process flash ID: got {self.chip_info!r}")
        return 0x200000

    def flash_get_rom_size(self) -> int:
        raise NotImplementedError("ROM is not readable via UART on RTL87xxB")

    def flash_read_raw(
        self,
        offset: int,
        length: int,
        verify: bool = True,
        use_rom: bool = False,
        callback: ProgressCallback = ProgressCallback(),
    ) -> Generator[bytes, None, None]:
        if use_rom:
            self.flash_get_rom_size()
        self.flash_connect()
        assert self.amb
        gen = self.amb.flash_read(
            offset=offset,
            length=length,
            hash_check=verify,
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
        try:
            self.amb.memory_write(
                address=AMBZ_FLASH_ADDRESS | offset,
                stream=data,
            )
            callback.detach(data)
        except Exception as e:
            callback.detach(data)
            raise e

    def flash_write_uf2(
        self,
        ctx: UploadContext,
        verify: bool = True,
        callback: ProgressCallback = ProgressCallback(),
    ) -> None:
        # read system data to get active OTA index
        callback.on_message("Checking OTA index...")
        system_data = gen2bytes(self.flash_read_raw(0x9000, 4096, verify=False))
        if len(system_data) != 4096:
            raise ValueError(
                f"Length invalid while reading from 0x9000 - {len(system_data)}"
            )
        system = SystemData.unpack(system_data)
        verbose(f"Realtek System Data: {system}")

        # read OTA switch value
        ota_switch = f"{system.ota2_switch:032b}"
        # count 0-bits
        ota_idx = 1 + (ota_switch.count("0") % 2)

        # check OTA2 address
        try:
            ota2_addr = system.ota2_address & 0xFFFFFF
            part_addr = ctx.get_offset("ota2", 0)
            if ota2_addr != part_addr:
                # if it differs, correct it
                system.ota2_address = AMBZ_FLASH_ADDRESS | part_addr
                # reset OTA switch to use OTA1
                system.ota2_switch = 0xFFFFFFFF
                ota_idx = 1
                # flash new system data
                system_data = system.pack()
                callback.on_message("Adjusting OTA2 address...")
                self.flash_write_raw(
                    offset=0x9000,
                    length=len(system_data),
                    data=BytesIO(system_data),
                    callback=callback,
                )
        except ValueError:
            warning("OTA2 partition not found in UF2 package")

        # collect continuous blocks of data
        parts = ctx.collect_data(
            OTAScheme.FLASHER_DUAL_1 if ota_idx == 1 else OTAScheme.FLASHER_DUAL_2
        )
        callback.on_total(sum(len(part.getvalue()) for part in parts.values()))

        callback.on_message(f"OTA {ota_idx}")
        # write blocks to flash
        for offset, data in parts.items():
            length = len(data.getvalue())
            data.seek(0)
            callback.on_message(f"OTA {ota_idx} (0x{offset:06X})")
            self.flash_write_raw(offset, length, data, verify, callback)

        callback.on_message("Booting firmware")
        self.amb.ram_boot(address=0x00005405)

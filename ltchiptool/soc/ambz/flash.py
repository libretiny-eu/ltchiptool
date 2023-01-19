# Copyright (c) Kuba Szczodrzyński 2022-07-29.

from abc import ABC
from io import BytesIO
from typing import IO, Generator, List, Optional, Union

from ltchiptool import SocInterface
from ltchiptool.util.flash import FlashConnection, ProgressCallback
from ltchiptool.util.intbin import gen2bytes, inttole32, letoint
from uf2tool import UploadContext

from .util.rtltool import CAN, RTL_ROM_BAUD, RTLXMD

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
    rtl: Optional[RTLXMD] = None

    def flash_set_connection(self, connection: FlashConnection) -> None:
        if self.conn:
            self.flash_disconnect()
        self.conn = connection
        self.conn.fill_baudrate(RTL_ROM_BAUD)

    def flash_build_protocol(self, force: bool = False) -> None:
        if not force and self.rtl:
            return
        self.flash_disconnect()
        self.rtl = RTLXMD(
            port=self.conn.port,
            baud=self.conn.link_baudrate,
            timeout=0.1,
        )
        self.flash_change_timeout(self.conn.timeout, self.conn.link_timeout)

    def flash_change_timeout(self, timeout: float = 0.0, link_timeout: float = 0.0):
        self.flash_build_protocol()
        if timeout:
            self.rtl._port.timeout = timeout
            self.conn.timeout = timeout
        if link_timeout:
            self.rtl.sync_timeout = link_timeout
            self.conn.link_timeout = link_timeout

    def flash_hw_reset(self) -> None:
        self.flash_build_protocol()
        self.rtl.connect()

    def flash_connect(self) -> None:
        if self.rtl and self.conn.linked:
            return
        self.flash_build_protocol()
        # try to exit interrupted write operations
        self.rtl._port.write(CAN)
        if not self.rtl.sync():
            raise TimeoutError(f"Failed to connect on port {self.conn.port}")
        self.conn.linked = True

    def flash_disconnect(self) -> None:
        if self.rtl:
            self.rtl._port.close()
            self.rtl._port = None
        self.rtl = None
        self.conn.linked = False

    def flash_get_chip_info_string(self) -> str:
        return "Realtek RTL87xxB"

    def flash_get_guide(self) -> List[Union[str, list]]:
        return AMEBAZ_GUIDE

    def flash_get_size(self) -> int:
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
        gen = self.rtl.ReadBlockFlashGenerator(offset, length)
        success = yield from callback.update_with(gen)
        if not success:
            raise ValueError(f"Failed to read from 0x{offset:X}")

    def flash_write_raw(
        self,
        offset: int,
        length: int,
        data: IO[bytes],
        verify: bool = True,
        callback: ProgressCallback = ProgressCallback(),
    ) -> None:
        self.flash_connect()
        offset |= 0x8000000
        callback.attach(data)
        success = self.rtl.WriteBlockFlash(data, offset, length)
        callback.detach(data)
        if not success:
            raise ValueError(f"Failed to write to 0x{offset:X}")

    def flash_write_uf2(
        self,
        ctx: UploadContext,
        verify: bool = True,
        callback: ProgressCallback = ProgressCallback(),
    ) -> None:
        # read system data to get active OTA index
        system = gen2bytes(self.flash_read_raw(0x9000, 256))
        if len(system) != 256:
            raise ValueError(
                f"Length invalid while reading from 0x9000 - {len(system)}"
            )
        # read OTA switch value
        ota_switch = f"{letoint(system[4:8]):032b}"
        # count 0-bits
        ota_idx = 1 + (ota_switch.count("0") % 2)
        # validate OTA2 address in system data
        if ota_idx == 2:
            ota2_addr = letoint(system[0:4]) & 0xFFFFFF
            part_addr = ctx.get_offset("ota2", 0)
            if ota2_addr != part_addr:
                raise ValueError(
                    f"Invalid OTA2 address on chip - "
                    f"found {ota2_addr}, expected {part_addr}",
                )

        # collect continuous blocks of data
        parts = ctx.collect(ota_idx=ota_idx)
        callback.on_total(sum(len(part.getvalue()) for part in parts.values()) + 4)

        callback.on_message(f"OTA {ota_idx}")
        # write blocks to flash
        for offset, data in parts.items():
            length = len(data.getvalue())
            callback.on_message(f"OTA {ota_idx} (0x{offset:06X})")
            data.seek(0)
            self.flash_write_raw(offset, length, data, verify, callback)

        callback.on_message("Booting firmware")
        # [0x10002000] = 0x00005405
        stream = BytesIO(inttole32(0x00005405))
        self.rtl.WriteBlockSRAM(stream, 0x10002000, 4)
        callback.on_update(4)

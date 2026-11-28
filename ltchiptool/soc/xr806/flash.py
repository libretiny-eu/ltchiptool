#  Copyright (c) 2026 bavci1988.

from abc import ABC
from logging import warning
from typing import IO, Generator, List, Optional, Tuple, Union

from ltchiptool import SocInterface
from ltchiptool.util.flash import FlashConnection, FlashMemoryType
from ltchiptool.util.streams import ProgressCallback
from uf2tool import OTAScheme, UploadContext

from .util import awih
from .util.xr806tool import (
    XR806_EFUSE_ADDRESS,
    XR806_EFUSE_SIZE,
    XR806_MAX_BAUDRATE,
    XR806_ROM_BAUDRATE,
    XR806_ROM_SIZE,
    XR806Tool,
)

XR806_DEFAULT_FLASH_SIZE = 0x200000

XR806_GUIDE = [
    "Connect UART0 of the XR806 to the USB-TTL adapter:",
    [
        ("PC", "XR806"),
        ("RX", "TX0 (PB00)"),
        ("TX", "RX0 (PB01)"),
        ("", ""),
        ("GND", "PB02 (BOOT, only while resetting)"),
        ("GND", "CHIP_PWD (reset, only briefly)"),
        ("", ""),
        ("GND", "GND"),
        ("3.3V", "VBAT / 3.3V"),
    ],
    "Tuya WXU module: TX0 is pad 15, RX0 is pad 16, PB02 is pad 17,\n"
    "CHIP_PWD (CEN) is pad 18, GND is pad 13 and 3.3V is pad 14.\n"
    "Bare XR806 (QFN32): TX0 is pin 29, RX0 is pin 28, PB02 is pin 25\n"
    "and CHIP_PWD is pin 15.",
    "On devices with an MCU (e.g. thermostats), UART0 is often also wired to the MCU.\n"
    "Disconnect the MCU or hold it in reset while flashing.",
    "Using a good, stable 3.3V power supply is crucial. Most flashing issues\n"
    "are caused by either voltage drops during intensive flash operations,\n"
    "or bad/loose wires. The 3.3V pin of most USB-TTL adapters is too weak.",
    "To enter download mode, connect PB02 to GND, then power-cycle the chip\n"
    "or connect CHIP_PWD to GND for a moment, while the flashing program is\n"
    "trying to establish communication. Remove PB02 from GND afterwards.\n"
    "A running SDK application may also enter download mode by itself when\n"
    "it receives the 'upgrade' command, which is sent first.",
]


class XR806Flash(SocInterface, ABC):
    xr806: Optional[XR806Tool] = None
    info: List[Tuple[str, str]] = None

    def flash_get_guide(self) -> List[Union[str, list]]:
        return XR806_GUIDE

    def flash_set_connection(self, connection: FlashConnection) -> None:
        if self.conn:
            self.flash_disconnect()
        self.conn = connection
        self.conn.fill_baudrate(XR806_MAX_BAUDRATE, XR806_ROM_BAUDRATE)

    def flash_build_protocol(self, force: bool = False) -> None:
        if not force and self.xr806:
            return
        self.flash_disconnect()
        self.xr806 = XR806Tool(
            port=self.conn.port,
            baudrate=self.conn.link_baudrate,
        )
        self.flash_change_timeout(self.conn.timeout, self.conn.link_timeout)

    def flash_change_timeout(self, timeout: float = 0.0, link_timeout: float = 0.0):
        self.flash_build_protocol()
        if timeout:
            self.xr806.read_timeout = timeout
            self.conn.timeout = timeout
        if link_timeout:
            self.xr806.link_timeout = link_timeout
            self.conn.link_timeout = link_timeout

    def flash_connect(self) -> None:
        if self.xr806 and self.conn.linked:
            return
        self.flash_build_protocol()
        assert self.xr806
        try:
            self.xr806.prepare(self.conn.baudrate)
        except (ValueError, RuntimeError) as e:
            # noise from a running application while linking; the caller retries on timeouts
            raise TimeoutError(f"No valid reply from the boot ROM: {e}")
        self.conn.linked = True

    def flash_disconnect(self) -> None:
        if self.xr806:
            try:
                if self.conn and self.conn.linked:
                    self.xr806.change_baudrate(XR806_ROM_BAUDRATE)
            except (TimeoutError, ValueError, RuntimeError):
                pass
            self.xr806.close()
        self.xr806 = None
        self.info = None
        if self.conn:
            self.conn.linked = False

    def flash_get_chip_info(self) -> List[Tuple[str, str]]:
        if self.info:
            return self.info
        self.flash_connect()
        assert self.xr806
        size = self.xr806.get_flash_size()
        self.info = [
            ("Chip Type", "XR806"),
            ("BROM Version", str(self.xr806.brom_version)),
            ("", ""),
            ("Flash ID", self.xr806.flash_id.hex(" ").upper()),
            ("Flash Size (by ID)", f"{size // 1024} KiB" if size else "Unknown"),
            ("", ""),
            *self._read_image_info(),
        ]
        return self.info

    def _read_header(self, offset: int, section_id: int) -> Tuple[int, ...]:
        """AWIH header fields at offset; only the header is read and checked."""
        data = b"".join(self.xr806.flash_read(offset, awih.HEADER.size))
        fields = awih.HEADER.unpack(data)
        if (
            fields[awih._MAGIC] != awih.AWIH_MAGIC
            or fields[awih._VERSION] != awih.AWIH_VERSION
            or awih.checksum16(data) != 0xFFFF
            or fields[awih._ID] != section_id
        ):
            raise ValueError(f"No AWIH section 0x{section_id:08X} at 0x{offset:X}")
        return fields

    def _read_image_info(self) -> List[Tuple[str, str]]:
        """Bootloader, application and OTA layout, from the AWIH headers in flash."""
        try:
            boot = self._read_header(0, awih.ID_BOOT)
        except ValueError:
            return [("Bootloader", "Not found (empty or foreign flash content)")]
        result = [
            ("Bootloader", f"{boot[awih._DATA_SIZE]} bytes"),
        ]
        app_offset = boot[awih._NEXT]
        try:
            app = self._read_header(app_offset, awih.ID_APP)
            result.append(
                ("Application", f"0x{app_offset:06X}, {app[awih._DATA_SIZE]} bytes")
            )
        except ValueError:
            result.append(("Application", f"Not found at 0x{app_offset:06X}"))
        ota_cfg = boot[awih._PRIV1]
        if ota_cfg == awih.NO_NEXT:
            result.append(("OTA Layout", "Not set (no OTA possible)"))
        else:
            ota_cfg_size = boot[awih._PRIV0] >> 8
            image_limit = (boot[awih._PRIV2] & 0xFFFF) * 1024
            slot_size = (boot[awih._PRIV2] >> 16) * 1024
            result += [
                ("Application Limit", f"0x{image_limit:06X}"),
                ("OTA Config (FDCM)", f"0x{ota_cfg:06X}"),
                (
                    "OTA Download Slot",
                    f"0x{ota_cfg + ota_cfg_size:06X}, {slot_size // 1024} KiB",
                ),
            ]
        return result

    def flash_get_chip_info_string(self) -> str:
        self.flash_connect()
        assert self.xr806
        return f"XR806 (BROM v{self.xr806.brom_version})"

    def flash_get_size(self, memory: FlashMemoryType = FlashMemoryType.FLASH) -> int:
        if memory == FlashMemoryType.ROM:
            return XR806_ROM_SIZE
        if memory == FlashMemoryType.EFUSE:
            return XR806_EFUSE_SIZE
        self.flash_connect()
        assert self.xr806
        size = self.xr806.get_flash_size()
        if not size:
            warning(
                f"Flash size not recognized from flash ID, using "
                f"{XR806_DEFAULT_FLASH_SIZE // 1024} KiB"
            )
            size = XR806_DEFAULT_FLASH_SIZE
        return size

    def flash_read_raw(
        self,
        offset: int,
        length: int,
        verify: bool = True,
        memory: FlashMemoryType = FlashMemoryType.FLASH,
        callback: ProgressCallback = ProgressCallback(),
    ) -> Generator[bytes, None, None]:
        self.flash_connect()
        assert self.xr806
        if memory != FlashMemoryType.FLASH:
            base = 0 if memory == FlashMemoryType.ROM else XR806_EFUSE_ADDRESS
            yield from self.xr806.memory_read(
                address=base + offset,
                length=length,
                callback=callback.on_update,
            )
            return
        yield from self.xr806.flash_read(
            offset=offset,
            length=length,
            callback=callback.on_update,
        )

    def flash_write_raw(
        self,
        offset: int,
        length: int,
        data: IO[bytes],
        verify: bool = True,
        callback: ProgressCallback = ProgressCallback(),
    ) -> None:
        self.flash_connect()
        assert self.xr806
        start = data.tell()
        self.xr806.flash_write(
            offset=offset,
            stream=data,
            length=length,
            callback=callback.on_update,
        )
        if not verify:
            return
        callback.on_message("Verifying")
        data.seek(start)
        for chunk in self.xr806.flash_read(offset, length):
            if chunk != data.read(len(chunk)):
                raise ValueError("Verification failed - flash data differs")

    def flash_write_uf2(
        self,
        ctx: UploadContext,
        verify: bool = True,
        callback: ProgressCallback = ProgressCallback(),
    ) -> None:
        # collect continuous blocks of data (before linking, as this takes time)
        parts = ctx.collect_data(OTAScheme.FLASHER_SINGLE)
        callback.on_total(sum(len(part.getvalue()) for part in parts.values()))

        self.flash_connect()

        for offset, data in parts.items():
            length = len(data.getvalue())
            data.seek(0)
            callback.on_message(f"Writing (0x{offset:06X})")
            self.flash_write_raw(
                offset=offset,
                data=data,
                length=length,
                verify=verify,
                callback=callback,
            )

        callback.on_message("Booting firmware")
        self.xr806.reboot()

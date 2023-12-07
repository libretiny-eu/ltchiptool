# Copyright (c) Kuba Szczodrzyński 2022-07-29.

import logging
import struct
from abc import ABC
from binascii import crc32
from logging import DEBUG, debug
from typing import IO, Generator, List, Optional, Tuple, Union

from bk7231tools.serial import BK7231Serial
from bk7231tools.serial.protocol import CHIP_BY_CRC

from ltchiptool import SocInterface
from ltchiptool.util.flash import FlashConnection, FlashFeatures, FlashMemoryType
from ltchiptool.util.intbin import gen2bytes, inttole32
from ltchiptool.util.logging import VERBOSE, verbose
from ltchiptool.util.misc import sizeof
from ltchiptool.util.streams import ProgressCallback
from uf2tool import OTAScheme, UploadContext

BK72XX_GUIDE = [
    "Connect UART1 of the BK7231 to the USB-TTL adapter:",
    [
        ("PC", "BK7231"),
        ("RX", "TX1 (GPIO11 / P11)"),
        ("TX", "RX1 (GPIO10 / P10)"),
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
    "In order to do that, you need to bridge CEN pin to GND with a wire.",
]

SCTRL_EFUSE_CTRL = 0x00800074
SCTRL_EFUSE_OPTR = 0x00800078


class BK72XXFlash(SocInterface, ABC):
    bk: Optional[BK7231Serial] = None
    info: List[Tuple[str, str]] = None

    def flash_get_features(self) -> FlashFeatures:
        return FlashFeatures()

    def flash_get_guide(self) -> List[Union[str, list]]:
        return BK72XX_GUIDE

    def flash_get_docs_url(self) -> Optional[str]:
        return "https://docs.libretiny.eu/link/flashing-beken-72xx"

    def flash_set_connection(self, connection: FlashConnection) -> None:
        if self.conn:
            self.flash_disconnect()
        self.conn = connection
        self.conn.fill_baudrate(115200)

    def flash_build_protocol(self, force: bool = False) -> None:
        if not force and self.bk:
            return
        self.flash_disconnect()
        self.bk = BK7231Serial(
            port=self.conn.port,
            baudrate=self.conn.baudrate,
            link_baudrate=self.conn.link_baudrate,
        )
        loglevel = logging.getLogger().getEffectiveLevel()
        if loglevel <= DEBUG:
            self.bk.info = lambda *args: debug(" ".join(args))
        if loglevel <= VERBOSE:
            self.bk.debug = lambda *args: verbose(" ".join(args))
        self.flash_change_timeout(self.conn.timeout, self.conn.link_timeout)

    def flash_change_timeout(self, timeout: float = 0.0, link_timeout: float = 0.0):
        self.flash_build_protocol()
        if timeout:
            self.bk.cmnd_timeout = timeout
            self.conn.timeout = timeout
        if link_timeout:
            self.bk.link_timeout = link_timeout
            self.conn.link_timeout = link_timeout

    def flash_hw_reset(self) -> None:
        self.flash_build_protocol()
        self.bk.hw_reset()

    def flash_connect(self) -> None:
        if self.bk and self.conn.linked:
            return
        self.flash_build_protocol()
        self.bk.connect()
        self.conn.linked = True

    def flash_disconnect(self) -> None:
        if self.bk:
            self.bk.close()
        self.bk = None
        if self.conn:
            self.conn.linked = False

    def flash_get_chip_info(self) -> List[Tuple[str, str]]:
        if self.info:
            return self.info
        self.flash_connect()
        crc = self.bk.read_flash_range_crc(0, 256) ^ 0xFFFFFFFF
        if crc in CHIP_BY_CRC:
            chip_type, boot_version = CHIP_BY_CRC[crc]
        else:
            chip_type = f"Unrecognized (0x{crc:08X})"
            boot_version = None
        self.info = [
            ("Chip Type", chip_type),
            ("Bootloader Version", boot_version or "Unspecified"),
        ]
        if self.bk.check_protocol(0x11):  # CMD_ReadBootVersion
            self.info.append(("Bootloader Message", self.bk.chip_info))
        if self.bk.check_protocol(0x03):  # CMD_ReadReg
            chip_id = hex(self.bk.register_read(0x800000))  # SCTRL_CHIP_ID
            self.info.append(("Chip ID", chip_id))
        self.info += [
            ("Protocol Type", self.bk.protocol_type.name),
        ]
        if chip_type == "BK7231N":
            tlv = self.bk.read_flash_4k(0x1D0000)
        elif chip_type == "BK7231T":
            tlv = self.bk.read_flash_4k(0x1E0000)
        else:
            tlv = None
        if tlv and tlv[0x1C:0x24] == b"\x02\x11\x11\x11\x06\x00\x00\x00":
            self.info += [
                ("", ""),
                ("MAC Address", tlv and tlv[0x24:0x2A].hex(":").upper() or "Unknown"),
            ]
        if self.bk.check_protocol(0x0E, True):  # CMD_FlashGetMID
            flash_id = self.bk.flash_read_id()
            self.info += [
                ("", ""),
                ("Flash ID", flash_id["id"].hex(" ").upper()),
                ("Flash Size (real)", sizeof(flash_id["size"])),
            ]
        if self.bk.check_protocol(0x03):  # CMD_ReadReg
            efuse = gen2bytes(self.flash_read_raw(0, 16, memory=FlashMemoryType.EFUSE))
            coeffs = struct.unpack("<IIII", efuse[0:16])
            self.info += [
                ("", ""),
                ("Encryption Key", " ".join(f"{c:08x}" for c in coeffs)),
            ]
        return self.info

    def flash_get_chip_info_string(self) -> str:
        self.flash_connect()
        return self.bk.chip_info

    def flash_get_size(self, memory: FlashMemoryType = FlashMemoryType.FLASH) -> int:
        self.flash_connect()
        if memory == FlashMemoryType.FLASH:
            if not self.bk.check_protocol(0x0E, True):  # CMD_FlashGetMID
                return 0x200000
            flash_id = self.bk.flash_read_id()
            return flash_id["size"]
        if memory == FlashMemoryType.ROM:
            if not self.bk.check_protocol(0x03):  # CMD_ReadReg
                raise NotImplementedError("Only BK7231N has built-in ROM")
            return 16 * 1024
        if memory == FlashMemoryType.EFUSE:
            if not self.bk.check_protocol(0x01):  # CMD_WriteReg
                raise NotImplementedError("Only BK7231N can read eFuse via UART")
            return 32
        raise NotImplementedError("Memory type not readable via UART")

    def flash_read_raw(
        self,
        offset: int,
        length: int,
        verify: bool = True,
        memory: FlashMemoryType = FlashMemoryType.FLASH,
        callback: ProgressCallback = ProgressCallback(),
    ) -> Generator[bytes, None, None]:
        self.flash_connect()

        if memory == FlashMemoryType.ROM:
            if offset % 4 != 0 or length % 4 != 0:
                raise ValueError("Offset and length must be 4-byte aligned")
            for address in range(offset, offset + length, 4):
                reg = self.bk.register_read(address)
                yield inttole32(reg)
                callback.on_update(4)
            return
        elif memory == FlashMemoryType.EFUSE:
            for addr in range(offset, offset + length):
                reg = self.bk.register_read(SCTRL_EFUSE_CTRL)
                reg = (reg & ~0x1F02) | (addr << 8) | 1
                self.bk.register_write(SCTRL_EFUSE_CTRL, reg)
                while reg & 1:
                    reg = self.bk.register_read(SCTRL_EFUSE_CTRL)
                reg = self.bk.register_read(SCTRL_EFUSE_OPTR)
                if reg & 0x100:
                    yield bytes([reg & 0xFF])
                    callback.on_update(1)
                else:
                    raise RuntimeError(f"eFuse data {addr} invalid: {hex(reg)}")
            return
        elif memory != FlashMemoryType.FLASH:
            raise NotImplementedError("Memory type not readable via UART")

        crc_offset = offset
        crc_length = 0
        crc_value = 0

        for chunk in self.bk.flash_read(start=offset, length=length, crc_check=False):
            if not verify:
                yield chunk
                continue

            crc_length += len(chunk)
            crc_value = crc32(chunk, crc_value)
            # check CRC every each 32 KiB, or by the end of file
            if crc_length < 32 * 1024 and crc_offset + crc_length != offset + length:
                yield chunk
                callback.on_update(len(chunk))
                continue

            debug(f"Checking CRC @ 0x{crc_offset:X}..0x{crc_offset+crc_length:X}")
            crc_expected = self.bk.read_flash_range_crc(
                crc_offset,
                crc_offset + crc_length,
            )
            if crc_expected != crc_value:
                raise ValueError(
                    f"Chip CRC value {crc_expected:X} does not match calculated "
                    f"CRC value {crc_value:X} (at 0x{crc_offset:X})"
                )
            crc_offset += crc_length
            crc_length = 0
            crc_value = 0
            yield chunk
            callback.on_update(len(chunk))

    def flash_write_raw(
        self,
        offset: int,
        length: int,
        data: IO[bytes],
        verify: bool = True,
        callback: ProgressCallback = ProgressCallback(),
    ) -> None:
        self.flash_connect()
        gen = self.bk.program_flash(
            io=data,
            io_size=length,
            start=offset,
            crc_check=verify,
        )
        callback.update_from(gen)

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
            gen = self.bk.program_flash(
                io=data,
                io_size=length,
                start=offset,
                crc_check=verify,
                dry_run=False,
                really_erase=True,
            )
            callback.update_from(gen)

        callback.on_message("Booting firmware")
        # reboot the chip
        self.bk.reboot_chip()

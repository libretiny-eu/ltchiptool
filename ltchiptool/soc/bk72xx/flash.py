# Copyright (c) Kuba Szczodrzyński 2022-07-29.

import logging
from abc import ABC
from binascii import crc32
from io import FileIO
from logging import DEBUG, debug, warning
from typing import BinaryIO, Generator, List, Optional, Tuple, Union

from bk7231tools.serial import BK7231Serial

from ltchiptool import SocInterface
from ltchiptool.soc.bk72xx.util import RBL, BekenBinary
from ltchiptool.util import CRC16, peek
from ltchiptool.util.intbin import betoint, gen2bytes
from ltchiptool.util.logging import VERBOSE, verbose
from uf2tool import UploadContext


def check_app_code_crc(data: bytes) -> Union[bool, None]:
    # b #0x40
    # ldr pc, [pc, #0x14]
    if data[0:8] == b"\x2F\x07\xB5\x94\x35\xFF\x2A\x9B":
        crc = CRC16.CMS.calc(data[0:32])
        crc_found = betoint(data[32:34])
        if crc == crc_found:
            return True
        warning("File CRC16 invalid. Considering as non-CRC file.")
        return
    return None


BK72XX_GUIDE = [
    "Connect UART1 of the BK7231 to the USB-TTL adapter:",
    [
        ("PC", "BK7231"),
        ("RX", "TX1 (GPIO11 / P11)"),
        ("TX", "RX1 (GPIO10 / P10)"),
        ("RTS", "CEN (or RST, optional)"),
        ("", ""),
        ("GND", "GND"),
    ],
    "Make sure to use a good 3.3V power supply, otherwise the adapter might\n"
    "lose power during chip reset. Usually, the adapter's power regulator\n"
    "is not enough and an external power supply is needed (like AMS1117).",
    "If you didn't connect RTS to CEN, after running the command you have\n"
    "around 20 seconds to reset the chip manually. In order to do that,\n"
    "you need to bridge CEN to GND with a wire.",
]


class BK72XXFlash(SocInterface, ABC):
    bk: Optional[BK7231Serial] = None
    is_linked: bool = False

    def flash_build_protocol(self, force: bool = False) -> None:
        if not force and self.bk:
            return
        self.flash_disconnect()
        self.bk = BK7231Serial(
            port=self.port,
            baudrate=self.baud,
            link_timeout=self.link_timeout,
            cmnd_timeout=self.read_timeout,
        )
        loglevel = logging.getLogger().getEffectiveLevel()
        if loglevel <= DEBUG:
            self.bk.info = lambda *args: debug(" ".join(args))
        if loglevel <= VERBOSE:
            self.bk.debug = lambda *args: verbose(" ".join(args))

    def flash_hw_reset(self) -> None:
        self.flash_build_protocol()
        self.bk.hw_reset()

    def flash_connect(self) -> None:
        if self.bk and self.is_linked:
            return
        self.flash_build_protocol()
        self.bk.connect()
        self.is_linked = True

    def flash_disconnect(self) -> None:
        if self.bk:
            self.bk.close()
        self.bk = None
        self.is_linked = False

    def flash_get_chip_info_string(self) -> str:
        self.flash_connect()
        items = [
            self.bk.chip_info,
            f"Flash ID: {self.bk.flash_id.hex(' ', -1) if self.bk.flash_id else None}",
            f"Protocol: {self.bk.protocol_type.name}",
        ]
        return " / ".join(items)

    def flash_get_guide(self) -> List[Union[str, list]]:
        return BK72XX_GUIDE

    def flash_get_size(self) -> int:
        return 0x200000

    def flash_get_file_type(
        self,
        file: FileIO,
        length: int,
    ) -> Optional[Tuple[str, Optional[int], int, int]]:
        data = peek(file, size=96)
        if not data:
            return None
        bk = BekenBinary()

        # app firmware file - opcodes encrypted for 0x10000
        app_code = check_app_code_crc(data)
        if app_code is None:
            pass
        elif app_code:
            return "Beken CRC App", 0x11000, 0, min(length, 0x121000)
        elif not app_code:
            return "Beken Encrypted App", None, 0, 0

        # raw firmware binary
        if data[0:8] == b"\x0E\x00\x00\xEA\x14\xF0\x9F\xE5":
            return "Raw ARM Binary", None, 0, 0

        # RBL file for OTA - 'download' partition
        try:
            rbl = RBL.deserialize(data)
            if rbl.encryption or rbl.compression:
                return "Beken OTA", None, 0, 0
        except ValueError:
            # no OTA RBL - continue checking
            pass

        # tried all known non-CRC formats - make sure CRC is okay
        try:
            bk.uncrc(data[0 : 34 * 2], check=True)
        except ValueError:
            # invalid CRC - nothing more to do
            return None

        # CRC is okay, but it's not app file - try to find bootloader RBL
        # read RBL+CRC and app opcodes
        data = peek(file, size=34 * 4, seek=0x10F9A)
        if not data:
            return None

        # file with bootloader - possibly a full dump
        try:
            rbl_data = gen2bytes(bk.uncrc(data[0 : 34 * 3], check=True))
            rbl = RBL.deserialize(rbl_data)
            if rbl.encryption or rbl.compression:
                return None
        except ValueError:
            # no bootloader RBL - give up
            return None

        # full dump file - encrypted app opcodes at 0x11000
        app_code = check_app_code_crc(data[34 * 3 : 34 * 4])
        if app_code:
            blocks = length // 1024
            if blocks == 2048:
                name = "Beken Full Dump"
            elif blocks == 1192:
                name = "Beken BL+APP Dump"
            else:
                name = "Beken Incomplete Dump"
            return name, 0x11000, 0x11000, min(length - 0x11000, 0x121000)

        return None

    def flash_read_raw(
        self,
        start: int,
        length: int,
        verify: bool = True,
        use_rom: bool = False,
    ) -> Generator[bytes, None, None]:
        self.flash_connect()

        crc_offset = start
        crc_length = 0
        crc_value = 0

        for chunk in self.bk.flash_read(start=start, length=length, crc_check=False):
            if not verify:
                yield chunk
                continue

            crc_length += len(chunk)
            crc_value = crc32(chunk, crc_value)
            # check CRC every each 32 KiB, or by the end of file
            if crc_length < 32 * 1024 and crc_offset + crc_length != start + length:
                yield chunk
                continue

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

    def flash_write_raw(
        self,
        start: int,
        length: int,
        data: BinaryIO,
        verify: bool = True,
    ) -> Generator[int, None, None]:
        self.flash_connect()
        yield from self.bk.program_flash(
            io=data,
            io_size=length,
            start=start,
            crc_check=verify,
        )

    def flash_write_uf2(
        self,
        ctx: UploadContext,
        verify: bool = True,
    ) -> Generator[Union[int, str], None, None]:
        # collect continuous blocks of data (before linking, as this takes time)
        parts = ctx.collect(ota_idx=1)

        # yield the total writing length
        yield sum(len(part.getvalue()) for part in parts.values())

        # connect to chip
        self.flash_connect()

        # write blocks to flash
        for offset, data in parts.items():
            length = len(data.getvalue())
            data.seek(0)
            yield f"Writing (0x{offset:06X})"
            yield from self.bk.program_flash(
                io=data,
                io_size=length,
                start=offset,
                crc_check=verify,
                dry_run=False,
                really_erase=True,
            )
        # reboot the chip
        self.bk.reboot_chip()

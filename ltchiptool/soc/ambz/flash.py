# Copyright (c) Kuba Szczodrzyński 2022-07-29.

from abc import ABC
from io import BytesIO
from logging import debug, warning
from time import sleep
from typing import IO, Generator, List, Optional, Tuple, Union

from hexdump import hexdump

from ltchiptool import SocInterface
from ltchiptool.soc.amb.efuse import efuse_physical_to_logical
from ltchiptool.soc.amb.system import SystemData
from ltchiptool.util.flash import FlashConnection, FlashFeatures, FlashMemoryType
from ltchiptool.util.intbin import gen2bytes, letoint
from ltchiptool.util.logging import verbose
from ltchiptool.util.misc import sizeof
from ltchiptool.util.streams import ProgressCallback
from uf2tool import OTAScheme, UploadContext

from .util.ambzcode import AmbZCode
from .util.ambztool import (
    AMBZ_CHIP_TYPE,
    AMBZ_EFUSE_LOGICAL_SIZE,
    AMBZ_EFUSE_PHYSICAL_SIZE,
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
        ("", ""),
        ("GND", "GND"),
    ],
    "Using a good, stable 3.3V power supply is crucial. Most flashing issues\n"
    "are caused by either voltage drops during intensive flash operations,\n"
    "or bad/loose wires.",
    "The UART adapter's 3.3V power regulator is usually not enough. Instead,\n"
    "a regulated bench power supply, or a linear 1117-type regulator is recommended.",
    "In order to flash the chip, you need to enable download mode.\n"
    "This is done by pulling CEN to GND briefly, while still keeping the TX2 pin\n"
    "connected to GND.",
    "Do this, in order:\n"
    " - connect CEN to GND\n"
    " - connect TX2 to GND\n"
    " - release CEN from GND\n"
    " - release TX2 from GND",
]


# noinspection PyProtectedMember
class AmebaZFlash(SocInterface, ABC):
    amb: Optional[AmbZTool] = None
    chip_id: int = None
    flash_id: bytes = None
    info: List[Tuple[str, str]] = None

    def flash_get_features(self) -> FlashFeatures:
        return FlashFeatures(
            can_read_rom=False,
        )

    def flash_get_guide(self) -> List[Union[str, list]]:
        return AMEBAZ_GUIDE

    def flash_get_docs_url(self) -> Optional[str]:
        return "https://docs.libretiny.eu/link/flashing-realtek-ambz"

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

    @staticmethod
    def _check_efuse(physical: bytes, logical: bytes) -> None:
        logical_read = logical
        logical_conv = efuse_physical_to_logical(physical)
        if logical_read != logical_conv:
            warning("eFuse Logical Map different from ROM and local conversion!")
            print("Read:")
            hexdump(logical_read)
            print("Converted:")
            hexdump(logical_conv)

    def flash_get_chip_info(self) -> List[Tuple[str, str]]:
        if self.info:
            return self.info
        self.flash_connect()
        assert self.amb

        data = self.amb.ram_boot_read(
            AmbZCode.read_efuse_raw(offset=0)
            + AmbZCode.read_efuse_logical_map(offset=256)
            + AmbZCode.read_flash_id(offset=256 + 512)
            + AmbZCode.print_data(length=256 + 512 + 16)
            + AmbZCode.print_data(length=16, address=0x400001F0)
            + AmbZCode.print_data(length=128, address=AMBZ_FLASH_ADDRESS | 0x9000)
        )
        if len(data) != 256 + 512 + 16 + 16 + 128:
            raise RuntimeError(
                f"Read data length invalid: " f"{len(data)} != {256+512+16+16+128}"
            )

        efuse_phys = data[0:256]
        efuse_logi = data[256:768]
        self.flash_id = data[768 : 768 + 3]
        self.chip_id = efuse_phys[0xF8]
        self._check_efuse(efuse_phys, efuse_logi)

        chip_type = AMBZ_CHIP_TYPE.get(self.chip_id, f"Unknown 0x{self.chip_id:02X}")
        size_id = self.flash_id[2]
        if 0x14 <= size_id <= 0x19:
            flash_size = sizeof(1 << size_id)
        else:
            flash_size = "Unknown"

        syscfg0 = letoint(data[256 + 512 + 16 + 0 : 256 + 512 + 16 + 0 + 4])
        syscfg1 = letoint(data[256 + 512 + 16 + 4 : 256 + 512 + 16 + 4 + 4])
        syscfg2 = letoint(data[256 + 512 + 16 + 8 : 256 + 512 + 16 + 8 + 4])

        system_data = data[256 + 512 + 16 + 16 : 256 + 512 + 16 + 16 + 128].ljust(
            4096, b"\xFF"
        )
        system = SystemData.unpack(system_data)

        return [
            ("Chip Type", chip_type),
            ("MAC Address", efuse_logi[0x11A : 0x11A + 6].hex(":").upper()),
            ("", ""),
            ("Flash ID", self.flash_id.hex(" ").upper()),
            ("Flash Size (real)", flash_size),
            ("", ""),
            ("OTA2 Address", f"0x{system.ota2_address:X}"),
            ("RDP Address", f"0x{system.rdp_address:X}"),
            ("RDP Length", f"0x{system.rdp_length:X}"),
            ("Flash SPI Mode", system.flash_mode.name),
            ("Flash SPI Speed", system.flash_speed.name[2:]),
            ("Flash ID (system)", f"{system.flash_id:04X}"),
            ("Flash Size (system)", sizeof(system.flash_size_mb << 20)),
            ("LOG UART Baudrate", system.baudrate),
            ("", ""),
            ("SYSCFG 0/1/2", f"{syscfg0:08X} / {syscfg1:08X} / {syscfg2:08X}"),
            ("ROM Version", f"V{syscfg2 >> 4}.{syscfg2 & 0xF}"),
            ("CUT Version", f"{(syscfg0 & 0xFF) >> 4:X}"),
        ]

    def flash_get_chip_info_string(self) -> str:
        if not self.chip_id or not self.flash_id:
            self.flash_connect()
            assert self.amb
            data = self.amb.ram_boot_read(
                AmbZCode.read_chip_id(offset=0)
                + AmbZCode.read_flash_id(offset=1)
                + AmbZCode.print_data(length=4)
            )
            self.chip_id = data[0]
            self.flash_id = data[1:4]
            debug(f"Received chip info: {data.hex()}")
        return AMBZ_CHIP_TYPE.get(self.chip_id, f"Unknown 0x{self.chip_id:02X}")

    def flash_get_size(self, memory: FlashMemoryType = FlashMemoryType.FLASH) -> int:
        if memory == FlashMemoryType.FLASH:
            if not self.flash_id:
                self.flash_get_chip_info_string()
            size_id = self.flash_id[2]
            if 0x14 <= size_id <= 0x19:
                return 1 << size_id
            warning(f"Couldn't process flash ID: got {self.flash_id.hex()}")
            return 0x200000
        if memory == FlashMemoryType.EFUSE:
            return AMBZ_EFUSE_PHYSICAL_SIZE
        raise NotImplementedError("Memory type not readable via UART")

    def flash_read_raw(
        self,
        offset: int,
        length: int,
        verify: bool = True,
        memory: FlashMemoryType = FlashMemoryType.FLASH,
        callback: ProgressCallback = ProgressCallback(),
    ) -> Generator[bytes, None, None]:
        if memory == FlashMemoryType.ROM:
            self.flash_get_size(memory)
        self.flash_connect()
        assert self.amb
        if memory == FlashMemoryType.FLASH:
            gen = self.amb.flash_read(
                offset=offset,
                length=length,
                hash_check=verify,
            )
            yield from callback.update_with(gen)
        elif memory == FlashMemoryType.EFUSE:
            data = self.amb.ram_boot_read(
                AmbZCode.read_efuse_raw(offset=0)
                + AmbZCode.read_efuse_logical_map(offset=AMBZ_EFUSE_PHYSICAL_SIZE)
                + AmbZCode.print_data(
                    length=AMBZ_EFUSE_PHYSICAL_SIZE + AMBZ_EFUSE_LOGICAL_SIZE
                )
            )
            self._check_efuse(
                physical=data[0:AMBZ_EFUSE_PHYSICAL_SIZE],
                logical=data[AMBZ_EFUSE_PHYSICAL_SIZE:],
            )
            yield data[offset : offset + length]

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

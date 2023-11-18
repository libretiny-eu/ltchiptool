#  Copyright (c) Kuba Szczodrzyński 2022-12-28.

from abc import ABC
from typing import IO, Generator, List, Optional, Tuple, Union

from ltchiptool import SocInterface
from ltchiptool.soc.amb.efuse import efuse_physical_to_logical
from ltchiptool.util.flash import FlashConnection, FlashFeatures, FlashMemoryType
from ltchiptool.util.intbin import gen2bytes, letoint
from ltchiptool.util.streams import ProgressCallback
from uf2tool import OTAScheme, UploadContext

from .util.ambz2code import AMBZ2_CODE_EFUSE_READ
from .util.ambz2tool import (
    AMBZ2_CHIP_TYPE,
    AMBZ2_CODE_ADDR,
    AMBZ2_DATA_ADDR,
    AMBZ2_EFUSE_PHYSICAL_SIZE,
    AmbZ2Tool,
)

AMEBAZ2_GUIDE = [
    "Connect UART2 of the Realtek chip to the USB-TTL adapter:",
    [
        ("PC", "RTL8720C"),
        ("RX", "TX2 (Log_TX / PA16)"),
        ("TX", "RX2 (Log_RX / PA15)"),
        ("", ""),
        ("GND", "GND"),
    ],
    "Using a good, stable 3.3V power supply is crucial. Most flashing issues\n"
    "are caused by either voltage drops during intensive flash operations,\n"
    "or bad/loose wires.",
    "The UART adapter's 3.3V power regulator is usually not enough. Instead,\n"
    "a regulated bench power supply, or a linear 1117-type regulator is recommended.",
    "In order to flash the chip, you need to enable download mode.\n"
    "This is similar to ESP8266/ESP32, but the strapping pin (GPIO 0 / PA00)\n"
    "has to be pulled *to 3.3V*, not GND.",
    "Additionally, make sure that pin PA13 (RX0) is NOT pulled to GND.",
    "Do this, in order:\n"
    " - connect PA00 to 3.3V\n"
    " - apply power to the device OR shortly connect CEN to GND\n"
    " - start the flashing process",
]


class AmebaZ2Flash(SocInterface, ABC):
    amb: Optional[AmbZ2Tool] = None
    chip_id: int = None
    flash_id: bytes = None
    info: List[Tuple[str, str]] = None

    def flash_get_features(self) -> FlashFeatures:
        return FlashFeatures()

    def flash_get_guide(self) -> List[Union[str, list]]:
        return AMEBAZ2_GUIDE

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

    def flash_get_chip_info(self) -> List[Tuple[str, str]]:
        if self.info:
            return self.info
        self.flash_connect()
        assert self.amb
        self.amb.flash_init(configure=False)

        efuse_phys = gen2bytes(
            self.flash_read_raw(
                offset=0,
                length=AMBZ2_EFUSE_PHYSICAL_SIZE,
                memory=FlashMemoryType.EFUSE,
            ),
        )
        efuse_logi = efuse_physical_to_logical(efuse_phys)
        # self.flash_id =
        self.chip_id = efuse_phys[0x1F8]

        chip_type = AMBZ2_CHIP_TYPE.get(self.chip_id, f"Unknown 0x{self.chip_id:02X}")
        # size_id = self.flash_id[2]
        # if 0x14 <= size_id <= 0x19:
        #     flash_size = sizeof(1 << size_id)
        # else:
        #     flash_size = "Unknown"

        syscfg0 = self.amb.register_read(0x4000_01F0)
        vid = (syscfg0 >> 8) & 0xF
        ver = (syscfg0 >> 4) & 0xF

        boot_debug = not (letoint(efuse_logi[0x18:0x1C]) & 0x100000)
        secure_boot = (efuse_logi[0x19] ^ 0x80) <= 0x7E

        self.info = [
            ("Chip VID", str(vid)),
            ("Chip Version", str(ver)),
            ("ROM Version", "v2.1" if ver <= 2 else "v3.0"),
            ("", ""),
            ("Chip Type", chip_type),
            ("MAC Address (Wi-Fi)", efuse_logi[0x11A : 0x11A + 6].hex(":").upper()),
            ("MAC Address (BT)", efuse_logi[0x190 : 0x190 + 6].hex(":").upper()),
            ("Boot Debugging", "Enabled" if boot_debug else "Disabled"),
            ("Secure Boot", "Enabled" if secure_boot else "Disabled"),
            ("", ""),
            # ("Flash ID", self.flash_id.hex(" ").upper()),
            # ("Flash Size (real)", flash_size),
            ("Flash Type", self.amb.flash_mode.name.replace("_", "/")),
            ("Flash Mode", self.amb.flash_speed.name),
        ]

        return self.info

    def flash_get_chip_info_string(self) -> str:
        self.flash_connect()
        assert self.amb
        self.amb.flash_init(configure=False)
        return self.amb.flash_mode.name.replace("_", "/")

    def flash_get_size(self, memory: FlashMemoryType = FlashMemoryType.FLASH) -> int:
        if memory == FlashMemoryType.FLASH:
            return 0x200000
        if memory == FlashMemoryType.ROM:
            return 384 * 1024
        if memory == FlashMemoryType.EFUSE:
            return AMBZ2_EFUSE_PHYSICAL_SIZE
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
        assert self.amb
        if memory == FlashMemoryType.EFUSE:
            self.amb.register_write_bytes(AMBZ2_CODE_ADDR, AMBZ2_CODE_EFUSE_READ)
            self.amb.memory_boot(AMBZ2_CODE_ADDR, force_find=True)
            offset |= AMBZ2_DATA_ADDR
        gen = self.amb.memory_read(
            offset=offset,
            length=length,
            use_flash=memory == FlashMemoryType.FLASH,
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
        try:
            self.amb.memory_write(
                offset=offset,
                stream=data,
                use_flash=True,
                hash_check=verify,
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
        callback.on_total(sum(len(part.getvalue()) for part in parts.values()))

        # write blocks to flash
        for offset, data in parts.items():
            length = len(data.getvalue())
            data.seek(0)
            callback.on_message(f"Writing (0x{offset:06X})")
            self.flash_write_raw(offset, length, data, verify, callback)

        callback.on_message("Booting firmware")
        self.amb.disconnect()

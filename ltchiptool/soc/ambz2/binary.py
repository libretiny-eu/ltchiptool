#  Copyright (c) Kuba Szczodrzyński 2023-1-21.

from abc import ABC
from os.path import isfile
from typing import IO, Dict, List, Optional

from ltchiptool import SocInterface
from ltchiptool.util.detection import Detection
from ltchiptool.util.fileio import chname, peek, readbin
from ltchiptool.util.fwbinary import FirmwareBinary
from ltchiptool.util.intbin import pad_data

from .util.models.config import ImageConfig
from .util.models.enums import ImageType, SectionType
from .util.models.headers import (
    EntryHeader,
    ImageHeader,
    Keyblock,
    KeyblockOTA,
    SectionHeader,
)
from .util.models.images import FLASH_CALIBRATION, Flash, Image
from .util.models.partitions import (
    Bootloader,
    Firmware,
    PartitionRecord,
    PartitionTable,
    Section,
)
from .util.models.utils import FF_32


class AmebaZ2Binary(SocInterface, ABC):
    @staticmethod
    def _get_public_key(private: bytes) -> bytes:
        from ltchiptool.util.curve25519 import X25519PrivateKey

        key = X25519PrivateKey.from_private_bytes(private)
        return key.public_key()

    def _build_keyblock(self, config: ImageConfig, region: str):
        if region in config.keys.keyblock:
            return Keyblock(
                decryption=self._get_public_key(config.keys.decryption),
                hash=self._get_public_key(config.keys.keyblock[region]),
            )
        return KeyblockOTA(
            decryption=self._get_public_key(config.keys.decryption),
        )

    def _build_section(
        self,
        section: ImageConfig.Section,
        input: str,
        nmap: Dict[str, int],
    ):
        toolchain = self.board.toolchain

        # build output name
        output = chname(input, f"raw.{section.name}.bin")
        # find entrypoint address
        entrypoint = nmap[section.entry]
        # objcopy sections to a binary file
        output = toolchain.objcopy(input, output, section.elf)
        # read the binary image
        data = readbin(output)
        # build EntryHeader
        entry = EntryHeader(
            address=entrypoint,
            entry_table=[entrypoint] if section.type == SectionType.SRAM else [],
        )
        # build Bootloader/Section struct
        if section.is_boot:
            data = pad_data(data, 0x20, 0x00)
            return Bootloader(
                entry=entry,
                data=data,
            )
        return Section(
            header=SectionHeader(type=section.type),
            entry=entry,
            data=data,
        )

    def elf2bin(self, input: str, ota_idx: int) -> List[FirmwareBinary]:
        result: Dict[str, Optional[int]] = {}
        # read AmbZ2 image config
        config = ImageConfig(**self.board["image"])
        # find partition offsets
        ptab_offset, _, ptab_end = self.board.region("part_table")
        boot_offset, _, boot_end = self.board.region("boot")
        ota1_offset, _, ota1_end = self.board.region("ota1")

        # find bootloader image
        input_boot = chname(input, "bootloader.axf")
        if not isfile(input_boot):
            raise FileNotFoundError("Bootloader image not found")
        # build output name
        output = FirmwareBinary(
            location=input,
            name="flash_is",
            offset=0,
            title="Flash Image",
        )
        out_ota1 = FirmwareBinary(
            location=input,
            name="firmware_is",
            offset=ota1_offset,
            title="Application Image",
            description="Firmware partition image for direct flashing",
            public=True,
        )
        out_ptab = FirmwareBinary(
            location=input,
            name="part_table",
            offset=ptab_offset,
            title="Partition Table",
        )
        out_boot = FirmwareBinary(
            location=input,
            name="bootloader",
            offset=boot_offset,
            title="Bootloader Image",
        )
        # print graph element
        output.graph(1)

        # return if images are up-to-date
        if all(binary.isnewer(than=input) for binary in output.group_get()):
            return output.group()

        # read addresses from input ELF
        nmap_boot = self.board.toolchain.nm(input_boot)
        nmap_ota1 = self.board.toolchain.nm(input)

        # build the partition table
        ptable = PartitionTable(user_data=b"\xFF" * 256)
        for region, type in config.ptable.items():
            offset, length, _ = self.board.region(region)
            hash_key = config.keys.hash_keys[region]
            ptable.partitions.append(
                PartitionRecord(offset, length, type, hash_key=hash_key),
            )
        ptable = Image(
            keyblock=self._build_keyblock(config, "part_table"),
            header=ImageHeader(
                type=ImageType.PARTAB,
            ),
            data=ptable,
        )

        # build boot image
        region = "boot"
        boot = Image(
            keyblock=self._build_keyblock(config, region),
            header=ImageHeader(
                type=ImageType.BOOT,
                user_keys=[config.keys.user_keys[region], FF_32],
            ),
            data=self._build_section(config.boot, input_boot, nmap_boot),
        )

        # build firmware (sub)images
        firmware = []
        region = "ota1"
        for idx, image in enumerate(config.fw):
            obj = Image(
                keyblock=self._build_keyblock(config, region),
                header=ImageHeader(
                    type=image.type,
                    # use FF to allow recalculating by OTA code
                    serial=0xFFFFFFFF if idx == 0 else 0,
                    user_keys=[FF_32, config.keys.user_keys[region]]
                    if idx == 0
                    else [FF_32, FF_32],
                ),
                data=Firmware(
                    sections=[
                        self._build_section(section, input, nmap_ota1)
                        for section in image.sections
                    ],
                ),
            )
            # remove empty sections
            obj.data.sections = [s for s in obj.data.sections if s.data]
            firmware.append(obj)
            if image.type != ImageType.XIP:
                continue
            # update SCE keys for XIP images
            for section in obj.data.sections:
                section.header.sce_key = config.keys.xip_sce_key
                section.header.sce_iv = config.keys.xip_sce_iv

        # build main flash image
        flash = Flash(
            ptable=ptable,
            boot=boot,
            firmware=firmware,
        )

        # write all parts to files
        data = flash.pack(hash_key=config.keys.hash_keys["part_table"])
        with output.write() as f:
            f.write(data)
        with out_ptab.write() as f:
            ptab = data[ptab_offset:ptab_end].rstrip(b"\xFF")
            ptab = pad_data(ptab, 0x20, 0xFF)
            f.write(ptab)
        with out_boot.write() as f:
            boot = data[boot_offset:boot_end].rstrip(b"\xFF")
            boot = pad_data(boot, 0x20, 0xFF)
            f.write(boot)
        with out_ota1.write() as f:
            ota1 = data[ota1_offset:ota1_end]
            f.write(ota1)
        return output.group()

    def detect_file_type(
        self,
        file: IO[bytes],
        length: int,
    ) -> Optional[Detection]:
        data = peek(file, size=0x1B0)
        if not data:
            return None

        if data.startswith(FLASH_CALIBRATION):
            return Detection.make("Realtek AmebaZ2 Flash Image", offset=0)

        if (
            data[0x40:0x44] != b"\xFF\xFF\xFF\xFF"
            and data[0x48] == ImageType.BOOT.value
        ):
            return Detection.make("Realtek AmebaZ2 Bootloader", offset=0x4000)

        if (
            data[0xE0:0xE8].strip(b"\xFF")
            and data[0xE8] == ImageType.FWHS_S.value
            and data[0x1A0:0x1A8].strip(b"\xFF")
            and data[0x1A8] == SectionType.SRAM.value
        ):
            return Detection.make("Realtek AmebaZ2 Firmware", offset=None)

        return None

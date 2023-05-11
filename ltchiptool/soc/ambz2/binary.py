#  Copyright (c) Kuba Szczodrzyński 2023-1-21.

from abc import ABC
from os.path import basename, isfile
from typing import Dict, Optional

from ltchiptool import SocInterface
from ltchiptool.util.fileio import chname, isnewer, readbin
from ltchiptool.util.intbin import pad_data
from ltchiptool.util.logging import graph

from .util.models.config import ImageConfig
from .util.models.enums import ImageType, SectionType
from .util.models.headers import (
    EntryHeader,
    ImageHeader,
    Keyblock,
    KeyblockOTA,
    SectionHeader,
)
from .util.models.images import Flash, Image
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
        output = chname(input, f"image.{section.name}.bin")
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

    def elf2bin(
        self,
        input: str,
        ota_idx: int,
    ) -> Dict[str, Optional[int]]:
        result: Dict[str, Optional[int]] = {}
        # read AmbZ2 image config
        config = ImageConfig(**self.board["image"])
        # find partition offsets
        boot_offset, _, boot_end = self.board.region("boot")
        ota1_offset, _, ota1_end = self.board.region("ota1")

        # find bootloader image
        input_boot = chname(input, "bootloader.axf")
        if not isfile(input_boot):
            raise FileNotFoundError("Bootloader image not found")
        # build output name
        output = chname(input, f"image_flash_is.0x{0:06X}.bin")
        out_ota1 = chname(input, f"image_firmware_is.0x{ota1_offset:06X}.bin")
        out_boot = chname(input, f"image_bootloader.0x{boot_offset:06X}.bin")
        # print graph element
        graph(1, basename(output))
        # add to outputs
        result[output] = 0
        result[out_boot] = boot_offset
        result[out_ota1] = ota1_offset

        # return if images are up-to-date
        if (
            not isnewer(input, output)
            and not isnewer(input, out_ota1)
            and not isnewer(input_boot, out_boot)
        ):
            return result

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
        with open(output, "wb") as f:
            f.write(data)
        with open(out_boot, "wb") as f:
            boot = data[boot_offset:boot_end].rstrip(b"\xFF")
            boot = pad_data(boot, 0x20, 0xFF)
            f.write(boot)
        with open(out_ota1, "wb") as f:
            ota1 = data[ota1_offset:ota1_end]
            f.write(ota1)
        return result

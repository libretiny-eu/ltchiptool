# Copyright (c) Kuba Szczodrzyński 2022-05-27.

from binascii import crc32
from logging import warning
from typing import IO, Tuple

from ltchiptool import Family
from ltchiptool.models import OTAType

from .binpatch import diff32_write
from .models import UF2, Block, Image, Tag
from .models.enums import OTAScheme

BLOCK_SIZE = 256


class UF2Writer:
    uf2: UF2
    family: Family

    def __init__(self, output: IO[bytes], family: Family):
        self.uf2 = UF2(output)
        self.uf2.family = family
        self.family = family

    def set_board(self, board: str):
        self.uf2.put_str(Tag.BOARD, board.lower())
        key = f"LibreTuya {board.lower()}"
        self.uf2.put_int32le(Tag.DEVICE_ID, crc32(key.encode()))

    def set_version(self, version: str):
        self.uf2.put_str(Tag.LT_VERSION, version)

    def set_firmware(self, fw: str):
        if ":" in fw:
            (fw_name, fw_ver) = fw.split(":")
            self.uf2.put_str(Tag.FIRMWARE, fw_name)
            self.uf2.put_str(Tag.VERSION, fw_ver)
        else:
            self.uf2.put_str(Tag.FIRMWARE, fw)

    def set_date(self, date: int):
        self.uf2.put_int32le(Tag.BUILD_DATE, date)

    def write(self, images: Tuple[Image]):
        from ltchiptool import SocInterface

        soc = SocInterface.get(self.family)

        self.uf2.put_int8(Tag.OTA_FORMAT_2, 2)
        self.uf2.put_str(Tag.DEVICE, "LibreTuya")

        for image in images:
            # local tags (for this image only)
            tags = {}

            if soc.ota_supports_format_1:
                single = image.schemes[OTAScheme.DEVICE_SINGLE]
                dual_1 = image.schemes[OTAScheme.DEVICE_DUAL_1]
                dual_2 = image.schemes[OTAScheme.DEVICE_DUAL_2]
                if single or dual_1 or dual_2:
                    if soc.ota_type == OTAType.SINGLE:
                        if single:
                            tags[Tag.LT_LEGACY_PART_1] = b""
                            tags[Tag.LT_LEGACY_PART_2] = single.encode()
                            self.uf2.put_int8(Tag.LT_LEGACY_HAS_OTA1, False)
                            self.uf2.put_int8(Tag.LT_LEGACY_HAS_OTA2, True)
                            self.uf2.put_int8(Tag.OTA_FORMAT_1, 1)
                        else:
                            warning(
                                "Legacy single-OTA format requested, but no "
                                "DEVICE_SINGLE target was provided. "
                                "Skipping legacy image generation. "
                                "Are you sure the input files match "
                                f"the '{self.family.description}' family?"
                            )
                    if soc.ota_type == OTAType.DUAL:
                        if dual_1 and dual_2:
                            tags[Tag.LT_LEGACY_PART_1] = dual_1.encode()
                            tags[Tag.LT_LEGACY_PART_2] = dual_2.encode()
                            self.uf2.put_int8(Tag.LT_LEGACY_HAS_OTA1, True)
                            self.uf2.put_int8(Tag.LT_LEGACY_HAS_OTA2, True)
                            self.uf2.put_int8(Tag.OTA_FORMAT_1, 1)
                        else:
                            warning(
                                "Legacy dual-OTA format requested, but either "
                                "DEVICE_DUAL_1 or DEVICE_DUAL_2 targets are missing. "
                                "Skipping legacy image generation. "
                                "Are you sure the input files match "
                                f"the '{self.family.description}' family?"
                            )

            tags[Tag.OTA_PART_INFO] = image.part_info
            data1 = image.read_file_1()
            data2 = image.read_file_2()
            if not data2:
                # single input file, write it at once
                self.uf2.store(image.offset, data1, tags, block_size=BLOCK_SIZE)
                continue
            # different images and/or partitions for each target
            if len(data1) != len(data2):
                raise ValueError(
                    f"Images must have same lengths ({len(data1)} vs {len(data2)})"
                )

            for i in range(0, len(data1), 256):
                block1 = data1[i : i + 256]
                block2 = data2[i : i + 256]
                if block1 != block2:
                    # calculate max binpatch length
                    # (incl. existing tags and binpatch tag header)
                    max_length = 476 - BLOCK_SIZE - Block.get_tags_length(tags) - 4
                    # try 32-bit binpatch for best space optimization
                    binpatch = diff32_write(block1, block2)
                    if len(binpatch) > max_length:
                        raise ValueError(
                            f"Binary patch too long - {len(binpatch)} > {max_length}"
                        )
                    tags[Tag.BINPATCH] = binpatch
                self.uf2.store(
                    address=image.offset + i,
                    data=block1,
                    tags=tags,
                    block_size=BLOCK_SIZE,
                )
                # store tags for the first block only
                tags = {}
        self.uf2.write()

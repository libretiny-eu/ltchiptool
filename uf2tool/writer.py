# Copyright (c) Kuba Szczodrzyński 2022-05-27.

from binascii import crc32
from io import FileIO
from typing import Tuple

from ltchiptool import Family

from .binpatch import diff32_write
from .models import UF2, Block, Input, Tag

BLOCK_SIZE = 256


class UF2Writer:
    uf2: UF2
    family: Family

    def __init__(self, output: FileIO, family: Family):
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

    def write(self, inputs: Tuple[Input]):
        self.uf2.put_int8(Tag.OTA_VERSION, 1)
        self.uf2.put_str(Tag.DEVICE, "LibreTuya")

        any_ota1 = False
        any_ota2 = False

        for input in inputs:
            any_ota1 = any_ota1 or input.has_ota1
            any_ota2 = any_ota2 or input.has_ota2

            # store local tags (for this image only)
            tags = {
                Tag.LT_PART_1: input.ota1_part.encode() if input.has_ota1 else b"",
                Tag.LT_PART_2: input.ota2_part.encode() if input.has_ota2 else b"",
            }

            if input.is_simple:
                # single input image:
                # - same image and partition (2 args)
                # - same image but different partitions (4 args)
                # - only OTA1 image
                # - only OTA2 image
                with open(input.single_file, "rb") as f:
                    data = f.read()
                self.uf2.store(input.single_offs, data, tags, block_size=BLOCK_SIZE)
                continue

            # different images and partitions for both OTA schemes
            with open(input.ota1_file, "rb") as f:
                data1 = f.read()
            with open(input.ota2_file, "rb") as f:
                data2 = f.read()

            if len(data1) != len(data2):
                raise ValueError(
                    f"Images must have same lengths ({len(data1)} vs {len(data2)})"
                )

            for i in range(0, len(data1), 256):
                block1 = data1[i : i + 256]
                block2 = data2[i : i + 256]
                if block1 == block2:
                    # blocks are identical, simply store them
                    self.uf2.store(
                        input.single_offs + i, block1, tags, block_size=BLOCK_SIZE
                    )
                    tags = {}
                    continue
                # calculate max binpatch length (incl. existing tags and binpatch tag header)
                max_length = 476 - BLOCK_SIZE - Block.get_tags_length(tags) - 4
                # try 32-bit binpatch for best space optimization
                binpatch = diff32_write(block1, block2)
                if len(binpatch) > max_length:
                    raise ValueError(
                        f"Binary patch too long - {len(binpatch)} > {max_length}"
                    )
                tags[Tag.LT_BINPATCH] = binpatch
                self.uf2.store(
                    input.single_offs + i, block1, tags, block_size=BLOCK_SIZE
                )
                tags = {}

        self.uf2.put_int8(Tag.LT_HAS_OTA1, any_ota1 * 1)
        self.uf2.put_int8(Tag.LT_HAS_OTA2, any_ota2 * 1)
        self.uf2.write()

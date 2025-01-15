# Copyright (c) Etienne Le Cousin 2025-01-02.

from abc import ABC
from datetime import datetime
from logging import warning
from os import stat
from os.path import basename, dirname, join, realpath
from typing import IO, List, Optional, Union
import json

from ltchiptool import SocInterface
from ltchiptool.util.fileio import chext
from ltchiptool.util.fwbinary import FirmwareBinary
from ltchiptool.util.lvm import LVM

from .util import MakeImageTool, OTATOOL


class LN882xBinary(SocInterface, ABC):
    def elf2bin(self, input: str, ota_idx: int) -> List[FirmwareBinary]:
        toolchain = self.board.toolchain

        bootfile = join(LVM.get().path(), f"cores", self.family.name, f"misc", self.board["build.bootfile"])
        part_cfg = join(dirname(input), "flash_partition_cfg.json")

        self.gen_partcfg_json(part_cfg)

        # build output names
        output_fw = FirmwareBinary(
            location=input,
            name=f"firmware",
            subname="",
            ext="bin",
            title="Flash Image",
            description="Complete image with boot for flashing at offset 0",
            public=True,
        )

        fw_bin = chext(input, "bin")
        # objcopy ELF -> raw BIN
        toolchain.objcopy(input, fw_bin)

        # Make firmware image
        mkimage = MakeImageTool()
        mkimage.boot_filepath       = bootfile
        mkimage.app_filepath        = fw_bin
        mkimage.flashimage_filepath = output_fw.path
        mkimage.part_cfg_filepath   = part_cfg
        mkimage.ver_str             = "1.0"
        mkimage.swd_crp             = 0
        mkimage.doAllWork()

        # Make ota image
        ota_tool = OTATOOL()
        ota_tool.input_filepath = output_fw.path
        ota_tool.output_dir     = dirname(input)
        ota_tool.doAllWork()

        output_ota = FirmwareBinary.load(
            location = ota_tool.output_filepath,
            obj = {
                "filename": basename(ota_tool.output_filepath),
                "title": "Flash OTA Image",
                "description": "Compressed App image for OTA flashing",
                "public": True,
            }
        )
        _, ota_size, _ = self.board.region("ota")
        if stat(ota_tool.output_filepath).st_size > ota_size:
            warning(
                f"OTA size too large: {ota_tool.output_filepath} > {ota_size} (0x{ota_size:X})"
            )

        return output_fw.group()

    def gen_partcfg_json(self, output: str):
        flash_layout = self.board["flash"]

        # find all partitions
        partitions = []
        for name, layout in flash_layout.items():
            part = {}
            (offset, _, length) = layout.partition("+")
            offset = int(offset, 16)
            length = int(length, 16)
            part["partition_type"] = name.upper()
            part["start_addr"]     = f"0x{offset:08X}"
            part["size_KB"]        = length // 1024
            partitions.append(part)

        partcfg: dict = {
            "vendor_define": [],        # boot and part_tab should be there but it's not needed
            "user_define": partitions   # so put all partitions in user define
            }
        # export file
        with open(output, "w") as f:
            json.dump(partcfg, f, indent="\t")


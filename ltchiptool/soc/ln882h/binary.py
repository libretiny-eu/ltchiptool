# Copyright (c) Etienne Le Cousin 2025-01-02.

from abc import ABC
from logging import warning
from os import stat
from os.path import dirname, isfile
from shutil import copyfile
from typing import List

from ltchiptool import SocInterface
from ltchiptool.util.fileio import chext, chname
from ltchiptool.util.fwbinary import FirmwareBinary

from .util import OTATOOL, MakeImageTool
from .util.models import PartDescInfo, part_type_str2num


class LN882hBinary(SocInterface, ABC):
    def elf2bin(self, input: str, ota_idx: int) -> List[FirmwareBinary]:
        toolchain = self.board.toolchain
        flash_layout = self.board["flash"]

        # find bootloader image
        input_boot = chname(input, "boot.bin")
        if not isfile(input_boot):
            raise FileNotFoundError("Bootloader image not found")

        # build output names
        output = FirmwareBinary(
            location=input,
            name="firmware",
            offset=0,
            title="Flash Image",
            description="Complete image with boot for flashing at offset 0",
            public=True,
        )
        out_boot = FirmwareBinary(
            location=input,
            name="boot",
            offset=self.board.region("boot")[0],
            title="Bootloader Image",
        )
        out_ptab = FirmwareBinary(
            location=input,
            name="part_tab",
            offset=self.board.region("part_tab")[0],
            title="Partition Table",
        )
        out_app = FirmwareBinary(
            location=input,
            name="app",
            offset=self.board.region("app")[0],
            title="Application Image",
            description="Firmware partition image for direct flashing",
            public=True,
        )
        out_ota = FirmwareBinary(
            location=input,
            name="ota",
            offset=self.board.region("ota")[0],
            title="OTA Image",
            description="Compressed App image for OTA flashing",
            public=True,
        )
        # print graph element
        output.graph(1)

        input_bin = chext(input, "bin")
        # objcopy ELF -> raw BIN
        toolchain.objcopy(input, input_bin)

        # Make Image Tool
        # fmt: off
        mkimage = MakeImageTool()
        mkimage.boot_filepath       = input_boot
        mkimage.app_filepath        = input_bin
        mkimage.flashimage_filepath = output.path
        mkimage.ver_str             = "1.0"
        mkimage.swd_crp             = 0
        mkimage.readPartCfg         = lambda : True
        # fmt: off

        # find all partitions
        for name, layout in flash_layout.items():
            (offset, _, length) = layout.partition("+")
            part_info = PartDescInfo(
                parttype = part_type_str2num(name.upper()),
                startaddr = int(offset, 16),
                partsize = int(length, 16)
            )
            mkimage._MakeImageTool__part_desc_info_list.append(part_info)

        if not mkimage.doAllWork():
            raise RuntimeError("MakeImageTool: Fail to generate image")

        # write all parts to files
        with out_boot.write() as f:
            f.write(mkimage._MakeImageTool__partbuf_bootram)
        with out_ptab.write() as f:
            f.write(mkimage._MakeImageTool__partbuf_parttab)
        with out_app.write() as f:
            f.write(mkimage._MakeImageTool__partbuf_app)

        # Make ota image
        ota_tool = OTATOOL()
        ota_tool.input_filepath = output.path
        ota_tool.output_dir     = dirname(input)
        if not ota_tool.doAllWork():
            raise RuntimeError("MakeImageTool: Fail to generate OTA image")

        copyfile(ota_tool.output_filepath, out_ota.path)
        _, ota_size, _ = self.board.region("ota")
        if stat(out_ota.path).st_size > ota_size:
            warning(
                f"OTA size too large: {out_ota.filename} > {ota_size} (0x{ota_size:X})"
            )

        return output.group()

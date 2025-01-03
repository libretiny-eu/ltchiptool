# Copyright (c) Etienne Le Cousin 2025-01-02.

from abc import ABC
from datetime import datetime
from logging import warning
from os import stat
from typing import IO, List, Optional, Union

from ltchiptool import SocInterface
from ltchiptool.util.detection import Detection
from ltchiptool.util.fileio import chext
from os.path import dirname, expanduser, isdir, isfile, join, realpath
from ltchiptool.util.fwbinary import FirmwareBinary

from ltchiptool.util.lvm import LVM

from .util import MakeImageTool


class LN882xBinary(SocInterface, ABC):
    def elf2bin(self, input: str, ota_idx: int) -> List[FirmwareBinary]:
        toolchain = self.board.toolchain
        lvm = LVM.get()
        print("lvm:", lvm.path())

        bootfile = self.board["build.bootfile"]
        flashpart = self.board["build.flashpart"]

        # build output names
        output = FirmwareBinary(
            location=input,
            name=f"firmware",
            subname="",
            ext="bin",
            title="Flash Image",
            description="Complete image with boot for flashing to ln882x memory at offset 0",
            public=True,
        )

        fw_bin = chext(input, "bin")
        # objcopy ELF -> raw BIN
        toolchain.objcopy(input, fw_bin)

        mkimage = MakeImageTool()
        mkimage.boot_filepath       = join(lvm.path(), f"cores", self.family.name, f"misc", bootfile)
        mkimage.app_filepath        = fw_bin
        mkimage.flashimage_filepath = output.path
        mkimage.part_cfg_filepath   = join(lvm.path(), f"cores", self.family.name, f"base/config", flashpart)
        mkimage.ver_str             = "1.0"
        mkimage.swd_crp             = 0
        mkimage.doAllWork()

        return output.group()

    def detect_file_type(
        self,
        file: IO[bytes],
        length: int,
    ) -> Optional[Detection]:

        return None

# Copyright (c) Kuba Szczodrzyński 2022-07-29.

from abc import ABC
from logging import error
from os import stat, unlink
from os.path import basename, isfile
from shutil import copyfile
from typing import Dict, List, Optional, Tuple

from ltchiptool.util.fileio import chext
from ltchiptool.util.logging import graph

from .interface import SocInterface


def ldargs_parse(
    args: List[str],
    ld_ota1: Optional[str],
    ld_ota2: Optional[str],
) -> List[Tuple[str, List[str]]]:
    args1 = list(args)
    args2 = list(args)
    elf1 = elf2 = None
    for i, arg in enumerate(args):
        if ".elf" in arg:
            if not ld_ota1:
                # single-OTA chip, return the output name
                return [(arg, args)]
            # append OTA index in filename
            args1[i] = elf1 = chext(arg, "ota1.elf")
            args2[i] = elf2 = chext(arg, "ota2.elf")
        if arg.endswith(".ld") and ld_ota1:
            # use OTA2 linker script
            args2[i] = arg.replace(ld_ota1, ld_ota2)
    if not elf1 or not elf2:
        raise ValueError("Linker output .elf not found in arguments")
    return [(elf1, args1), (elf2, args2)]


def checkfile(path: str):
    if not isfile(path) or stat(path).st_size == 0:
        error(f"Generated file not found: {path}")
        exit(1)


class SocInterfaceCommon(SocInterface, ABC):
    def link2elf(
        self,
        ota1: str,
        ota2: str,
        args: List[str],
    ) -> Dict[int, str]:
        toolchain = self.board.toolchain

        if self.elf_has_dual_ota:
            # process linker arguments for dual-OTA chips
            elfs = ldargs_parse(args, ota1, ota2)
        else:
            # just get .elf output name for single-OTA chips
            elfs = ldargs_parse(args, None, None)

        ota_idx = 1
        for elf, ldargs in elfs:
            graph(0, f"Image {ota_idx}: {basename(elf)}")
            if isfile(elf):
                unlink(elf)
            toolchain.cmd(f"gcc", args=ldargs).read()
            checkfile(elf)
            ota_idx += 1

        if self.elf_has_dual_ota:
            # copy OTA1 file as firmware.elf to make PIO understand it
            elf, _ = ldargs_parse(args, None, None)[0]
            copyfile(elfs[0][0], elf)

        return {ota_idx + 1: elf for ota_idx, (elf, _) in enumerate(elfs)}

    def link2bin(
        self,
        ota1: str,
        ota2: str,
        args: List[str],
    ) -> Dict[str, Optional[int]]:
        elfs = self.link2elf(ota1, ota2, args)
        output = {}

        for ota_idx, elf in elfs.items():
            # generate a set of binaries for the SoC
            bins = self.elf2bin(elf, ota_idx)
            output.update(bins)
        return output

# Copyright (c) Kuba Szczodrzyński 2022-07-29.

import shlex
from os import stat, unlink
from os.path import basename, isfile
from shutil import copyfile
from typing import List, Optional, Tuple

import click

from ltchiptool import Board, SocInterface
from ltchiptool.models import BoardParamType
from ltchiptool.util import chext, readtext


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
        print(f"Generated file not found: {path}")
        exit(1)


@click.command(context_settings={"ignore_unknown_options": True})
@click.argument("board", type=BoardParamType())
@click.argument("ota1")
@click.argument("ota2")
@click.argument("args", nargs=-1)
def cli(board: Board, ota1: str, ota2: str, args: Tuple[str]):
    """
    Link code to binary format

    \b
    Arguments:
      BOARD  Target board name
      OTA1   .LD file OTA1 pattern
      OTA2   .LD file OTA2 pattern
      ARGS   SoC+linker arguments
    """
    args = list(args)
    try:
        while True:
            i = next(i for i, a in enumerate(args) if a.startswith("@"))
            arg = args.pop(i)
            argv = readtext(arg[1:])
            argv = shlex.split(argv)
            args = args[0:i] + argv + args[i:]
    except StopIteration:
        pass

    soc = SocInterface.get(board.family)
    toolchain = board.toolchain

    if soc.elf_has_dual_ota:
        # process linker arguments for dual-OTA chips
        elfs = ldargs_parse(args, ota1, ota2)
    else:
        # just get .elf output name for single-OTA chips
        elfs = ldargs_parse(args, None, None)

    ota_idx = 1
    for elf, ldargs in elfs:
        # print graph element
        print(f"|-- Image {ota_idx}: {basename(elf)}")
        if isfile(elf):
            unlink(elf)
        toolchain.cmd(f"gcc", args=ldargs).read()
        checkfile(elf)
        # generate a set of binaries for the SoC
        soc.elf2bin(board, elf, ota_idx)
        ota_idx += 1

    if soc.elf_has_dual_ota:
        # copy OTA1 file as firmware.elf to make PIO understand it
        elf, _ = ldargs_parse(args, None, None)[0]
        copyfile(elfs[0][0], elf)

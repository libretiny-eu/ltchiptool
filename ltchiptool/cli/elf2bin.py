# Copyright (c) Kuba Szczodrzyński 2022-07-29.

import click

from ltchiptool import Board, SocInterface
from ltchiptool.models import BoardParamType


@click.command()
@click.argument("board", type=BoardParamType())
@click.argument("input", type=click.Path(exists=True, dir_okay=False))
@click.argument("ota_idx", type=int)
def cli(board: Board, input: str, ota_idx: int):
    """
    Generate firmware binaries from ELF file

    \b
    Arguments:
      BOARD    Target board name
      INPUT    ELF input file
      OTA_IDX  OTA index of the input file
    """
    soc = SocInterface.get(board.family)
    files = soc.elf2bin(board, input, ota_idx)
    print("Generated files:")
    for name, offset in files.items():
        if offset is None:
            print(f" - {name}")
        else:
            print(f" - {name} - flashable at 0x{offset:X}")

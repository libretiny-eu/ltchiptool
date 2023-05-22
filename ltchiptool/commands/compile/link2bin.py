# Copyright (c) Kuba Szczodrzyński 2022-07-29.

from typing import Tuple

import click

from ltchiptool import Board, SocInterface
from ltchiptool.models import BoardParamType
from ltchiptool.util.cli import parse_argfile


@click.command(
    context_settings=dict(
        ignore_unknown_options=True,
        help_option_names=["--help"],
    )
)
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
    args = parse_argfile(args)
    soc = SocInterface.get(board.family)
    soc.set_board(board)
    soc.link2bin(ota1, ota2, args)

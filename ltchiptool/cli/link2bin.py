# Copyright (c) Kuba Szczodrzyński 2022-07-29.

import click


@click.command(context_settings={"ignore_unknown_options": True})
@click.argument("board")
@click.argument("ota1")
@click.argument("ota2")
@click.argument("args", nargs=-1)
def cli():
    """
    Link code to binary format

    \b
    Arguments:
      BOARD  Target board name
      OTA1   .LD file OTA1 pattern
      OTA2   .LD file OTA2 pattern
      ARGS   SoC+linker arguments
    """

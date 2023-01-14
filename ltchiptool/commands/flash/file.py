#  Copyright (c) Kuba Szczodrzyński 2022-12-23.

from io import SEEK_SET
from logging import debug, info
from typing import IO

import click
from click import File

from ltchiptool import Family
from ltchiptool.models import FamilyParamType
from ltchiptool.util.cli import AutoIntParamType
from ltchiptool.util.detection import Detection
from ltchiptool.util.logging import verbose


@click.command(short_help="Detect file type")
@click.argument("file", type=File("rb"))
@click.option(
    "-f",
    "--family",
    help="Chip family name/code (default: based on file type)",
    type=FamilyParamType(by_parent=True),
)
@click.option(
    "-S",
    "--skip",
    help="Amount of bytes to skip from **input file** (default: 0)",
    type=AutoIntParamType(),
)
def cli(
    file: IO[bytes],
    family: Family,
    skip: int,
):
    """
    Scan the file and check its type.

    When -f/--family is specified, file checks of other SoC families won't be performed.

    \b
    Arguments:
      FILE      Input file name
    """
    if skip is not None:
        # ignore the skipped bytes entirely
        file.seek(skip, SEEK_SET)
    detection = Detection.perform(file, family)
    info(f"{detection.name}: {detection.title} ({detection.type})")
    verbose(f"\tdetection={detection}")
    if detection.family is not None:
        debug(f"\tfamily={detection.family}")
    if detection.offset is not None:
        debug(f"\toffset=0x{detection.offset:X}")
    if detection.skip is not None:
        debug(f"\tskip=0x{detection.skip:X}")
    if detection.length is not None:
        debug(f"\tlength=0x{detection.length:X}")

#  Copyright (c) Kuba Szczodrzyński 2022-12-23.

from io import SEEK_SET, FileIO
from logging import debug, info

import click
from click import File

from ltchiptool import Family
from ltchiptool.models import FamilyParamType
from ltchiptool.util import AutoIntParamType

from ._utils import get_file_type


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
    file: FileIO,
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
    file_type, family, _, offset, skip, length = get_file_type(family, file)
    info(f"{file.name}: {file_type or 'Unrecognized'}")
    debug(f"\tfamily={family}")
    debug(f"\toffset={offset}")
    debug(f"\tskip={skip}")
    debug(f"\tlength={length}")

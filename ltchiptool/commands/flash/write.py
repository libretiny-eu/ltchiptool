#  Copyright (c) Kuba Szczodrzyński 2022-12-23.

from io import SEEK_CUR, SEEK_SET, FileIO
from logging import debug, error, fatal
from os import stat
from time import time

import click
from click import File

from ltchiptool import Family, SocInterface
from ltchiptool.models import FamilyParamType
from ltchiptool.util import AutoIntParamType, DevicePortParamType, graph, sizeof

from ._utils import flash_link_interactive, get_file_type


@click.command(short_help="Write flash contents")
@click.argument("file", type=File("rb"))
@click.option(
    "-d",
    "--device",
    help="Target device port (default: auto detect)",
    type=DevicePortParamType(),
    default=(),
)
@click.option(
    "-b",
    "--baudrate",
    help="UART baud rate (default: auto choose)",
    type=int,
)
@click.option(
    "-f",
    "--family",
    help="Chip family name/code (default: based on file type)",
    type=FamilyParamType(by_parent=True),
)
@click.option(
    "-s",
    "--start",
    help="Starting address to read from (default: based on file type)",
    type=AutoIntParamType(),
)
@click.option(
    "-S",
    "--skip",
    help="Amount of bytes to skip from **input file** (default: based on file type)",
    type=AutoIntParamType(),
)
@click.option(
    "-l",
    "--length",
    help="Length to write, in bytes (default: based on file type)",
    type=AutoIntParamType(),
)
@click.option(
    "-t",
    "--timeout",
    help="Timeout for operations in seconds (default: 20.0)",
    type=float,
    default=None,
)
@click.option(
    "-c/-C",
    "--check/--no-check",
    help="Check hash/CRC of the written data (default: True)",
    default=True,
)
def cli(
    file: FileIO,
    device: str,
    baudrate: int,
    family: Family,
    start: int,
    skip: int,
    length: int,
    timeout: float,
    check: bool,
):
    """
    Upload a file to the chip's flash.

    The program tries to auto-detect the input file type.
    The -f/--family, -s/--start, -S/--skip and -l/--length are
    then chosen automatically to best match the file.

    \b
    - specifying only -f/--family will still try to detect the other options
    - specifying only -s/--start is not possible and requires -f/--family as well
    - specifying -S/--skip will only consider the file after skipping
    - specifying -f/--family and -s/--start disables the auto-detection entirely

    Note that flashing unrecognized files is possible, but requires -f/--family and -s/--start.

    When not specified (-d), the first UART port is used. The baud rate (-b)
    is chosen automatically, depending on the chip capabilities.

    \b
    Arguments:
      FILE      File name to write
    """
    time_start = time()
    if skip is not None:
        # ignore the skipped bytes entirely
        file.seek(skip, SEEK_SET)
    file_size = stat(file.name).st_size - (skip or 0)

    if family is None and start is not None:
        # not possible
        error("Specifying -s/--start without -f/--family is not possible")
        return

    ctx = None
    if family and start is not None:
        file_type = "Raw"
        soc = auto_start = auto_skip = auto_length = None
    else:
        # perform auto-detection
        file_type, family, soc, auto_start, auto_skip, auto_length = get_file_type(
            family, file
        )

    if not file_type:
        # file type not found using auto-detection
        error(
            f"'{file.name}' is of an unknown type. "
            f"To flash raw files, use -f/--family and -s/--start."
        )
        return

    # different handling of common file types
    if file_type == "UF2":
        if family is not None:
            error("Can't specify -f/--family for flashing UF2 files")
            return
        if length:
            error("Can't specify -s/--start and -l/--length for flashing UF2 files")
            return
        from uf2tool import UploadContext
        from uf2tool.models import UF2

        uf2 = UF2(file)
        uf2.read(block_tags=False)
        ctx = UploadContext(uf2)
        family = ctx.board.family
    elif file_type != "Raw" and not family:
        # file is of a common type (from FILE_TYPES)
        error(f"'{file.name}' is a '{file_type}' file - it's not directly flashable")
        return

    if soc and auto_start is None:
        # file type found using SocInterface, but marked as not flashable
        error(
            f"'{file.name}' is a '{file_type}' file - it's not "
            f"directly flashable to '{family.description}'"
        )
        return

    # 1. file type found using SocInterface
    # 2. flashing in Raw mode (-f + -s)
    # 3. common file type (UF2 only, for now)
    if not family:
        fatal("Unknown error in parameter processing logic")
        return
    if not soc:
        soc = SocInterface.get(family)
    flash_link_interactive(soc, device, baudrate, timeout)

    graph(0, f"Writing '{file.name}' ({file_type}) to '{family.description}'")
    if ctx:
        graph(1, ctx.fw_name, ctx.fw_version, "@", ctx.build_date, "->", ctx.board_name)
        generator = soc.flash_write_uf2(ctx)
    else:
        if start is None:
            start = auto_start
        else:
            auto_start = None

        if length is None:
            length = auto_length
        else:
            auto_length = None

        if not length:
            length = file_size - (auto_skip or 0)
            auto_length = None

        auto_str = " (auto-detected)"
        length_str = sizeof(length) if length else None
        skip_str = sizeof(skip) if skip else None
        auto_skip_str = sizeof(auto_skip) if auto_skip else None
        total_skip_str = sizeof(skip + auto_skip) if skip and auto_skip else None

        graph(1, f"Start offset: 0x{start:X}" + (auto_str if auto_start else ""))
        graph(1, f"Write length: {length_str}" + (auto_str if auto_length else ""))
        if total_skip_str:
            graph(1, f"Skipped data: {skip_str} + {auto_skip_str} = {total_skip_str}")
        elif skip_str:
            graph(1, f"Skipped data: {skip_str}")
        elif auto_skip_str:
            graph(1, f"Skipped data: {auto_skip_str}" + auto_str)

        if (auto_skip or 0) + length > file_size or length <= 0:
            error(f"File is too small")
            return
        flash_size = soc.flash_get_size()
        if start + length > flash_size:
            error(f"Flash is too small")
            return

        if auto_skip:
            file.seek(auto_skip, SEEK_CUR)
        tell = file.tell()
        debug(f"Starting file position: {tell} / 0x{tell:X} / {sizeof(tell)}")
        generator = soc.flash_write_raw(start, length, data=file, verify=check)

    for _ in generator:
        pass

    duration = time() - time_start
    graph(1, f"Finished in {duration:.3f} s")

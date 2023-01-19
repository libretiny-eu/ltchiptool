#  Copyright (c) Kuba Szczodrzyński 2022-12-23.

from io import SEEK_SET
from logging import debug, fatal
from time import time
from typing import IO

import click
from click import File

from ltchiptool import Family, SocInterface
from ltchiptool.models import FamilyParamType
from ltchiptool.util.cli import AutoIntParamType, DevicePortParamType
from ltchiptool.util.detection import Detection
from ltchiptool.util.flash import ClickProgressCallback, FlashConnection
from ltchiptool.util.logging import graph
from ltchiptool.util.misc import sizeof
from uf2tool import UploadContext

from ._utils import flash_link_interactive


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
    "offset",
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
    help="Chip connection timeout in seconds (default: 20.0)",
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
    file: IO[bytes],
    device: str,
    baudrate: int,
    family: Family,
    offset: int,
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

    Note that flashing unrecognized files is possible,
    but requires -f/--family and -s/--start.

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

    if family is None and offset is not None:
        # not possible
        raise ValueError("Specifying -s/--start without -f/--family is not possible")

    if family and offset is not None:
        detection = Detection.make_raw(file)
    else:
        # perform auto-detection
        detection = Detection.perform(file, family)
    debug(f"Detection: {detection}")

    if detection.type == Detection.Type.UNRECOGNIZED:
        raise ValueError(
            f"'{file.name}' is of an unknown type. "
            f"To flash raw files, use -f/--family and -s/--start.",
        )
    elif detection.type == Detection.Type.UNSUPPORTED:
        raise ValueError(
            f"'{file.name}' is a '{detection.title}' file - it's not directly flashable"
        )
    elif detection.type == Detection.Type.UNSUPPORTED_HERE:
        raise ValueError(
            f"'{file.name}' is a '{detection.title}' file - it's not "
            f"directly flashable to '{detection.family.description}'",
        )
    elif detection.type == Detection.Type.UNSUPPORTED_UF2:
        raise ValueError(f"'{file.name}' is UF2 of unsupported family")
    elif detection.type == Detection.Type.VALID_UF2:
        if family is not None:
            raise ValueError(
                "Can't specify -f/--family " "for flashing UF2 files",
            )
        if length:
            raise ValueError(
                "Can't specify -s/--start and -l/--length for flashing UF2 files",
            )
    elif detection.type == Detection.Type.VALID_NEED_OFFSET:
        raise ValueError(
            f"'{file.name}' is a '{detection.title}' file - it's flashable "
            f"but needs a manually specified start offset",
        )

    if detection.type != Detection.Type.RAW:
        graph(0, f"Detected file type: {detection.title}")
    family = detection.family
    soc = detection.soc
    uf2 = detection.uf2

    # 1. file type found using SocInterface
    # 2. flashing in Raw mode (-f + -s)
    # 3. common file type (UF2 only, for now)
    if not family:
        fatal("Unknown error in parameter processing logic")
        return
    if not soc:
        soc = SocInterface.get(family)
    soc.flash_set_connection(FlashConnection(device, baudrate))
    flash_link_interactive(soc, timeout)

    graph(0, f"Writing '{file.name}'")
    callback = ClickProgressCallback()
    if uf2:
        ctx = UploadContext(uf2)
        graph(1, ctx.fw_name, ctx.fw_version, "@", ctx.build_date, "->", ctx.board_name)
        soc.flash_write_uf2(ctx, verify=check, callback=callback)
    else:
        if offset is not None:
            detection.offset = offset
        if length:
            detection.length = length
        if skip:
            detection.size += skip
            detection.skip += skip

        auto_str = " (auto-detected)"
        graph(
            1,
            f"Start offset: 0x{detection.offset:X}"
            + (auto_str if offset is None else ""),
        )
        graph(
            1,
            f"Write length: {sizeof(detection.length)}"
            + (auto_str if length is None else ""),
        )
        graph(
            1,
            f"Skipped data: {sizeof(detection.skip)}"
            + (auto_str if skip is None else ""),
        )

        if detection.skip + detection.length > detection.size:
            raise ValueError(f"File is too small")

        max_length = soc.flash_get_size()
        if detection.offset + detection.length > max_length:
            raise ValueError(
                f"Writing length {sizeof(detection.length)} @ 0x{detection.offset:X} "
                f"is more than chip capacity ({sizeof(max_length)})",
            )

        file.seek(detection.skip, SEEK_SET)
        tell = file.tell()
        debug(f"Starting file position: {tell} / 0x{tell:X} / {sizeof(tell)}")
        callback.on_total(detection.length)
        soc.flash_write_raw(
            offset=detection.offset,
            length=detection.length,
            data=file,
            verify=check,
            callback=callback,
        )
    callback.finish()

    duration = time() - time_start
    graph(1, f"Finished in {duration:.3f} s")

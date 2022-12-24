#  Copyright (c) Kuba Szczodrzyński 2022-12-23.

from io import SEEK_CUR, SEEK_SET, FileIO
from logging import WARNING, debug, error, fatal, info, warning
from os import stat
from time import time
from typing import Optional, Tuple

import click
from click import File

from ltchiptool import Family, SocInterface
from ltchiptool.models import FamilyParamType
from ltchiptool.util import AutoIntParamType, graph, peek, sizeof

FILE_TYPES = {
    "UF2": [
        (0x000, b"UF2\x0A"),
        (0x004, b"\x57\x51\x5D\x9E"),
        (0x1FC, b"\x30\x6F\xB1\x0A"),
    ],
    "ELF": [
        (0x00, b"\x7FELF"),
    ],
    "Tuya UG": [
        (0x00, b"\x55\xAA\x55\xAA"),
        (0x1C, b"\xAA\x55\xAA\x55"),
    ],
}


def find_serial_port() -> Optional[str]:
    from serial.tools.list_ports import comports

    ports = {}
    graph(0, "Available COM ports:")
    for port in comports():
        is_usb = port.hwid.startswith("USB")
        if is_usb:
            description = (
                f"{port.name} - {port.description} - "
                f"VID={port.vid:04X} ({port.manufacturer}), "
                f"PID={port.pid:04X} "
            )
        else:
            description = f"{port.name} - {port.description} - HWID={port.hwid}"
        ports[port.device] = [is_usb, description]

    ports = sorted(ports.items(), key=lambda x: (not x[1][0], x[1][1]))
    if not ports:
        warning("No COM ports found! Use -d/--device to specify the port manually.")
        return None
    for idx, (_, (is_usb, description)) in enumerate(ports):
        graph(1, description)
        if idx == 0:
            graph(2, "Selecting this port. To override, use -d/--device")
            if not is_usb:
                graph(2, "This is not a USB COM port", loglevel=WARNING)
    return ports[0][0]


def get_file_type(
    family: Optional[Family],
    file: FileIO,
) -> Optional[
    Tuple[
        str,
        Optional[Family],
        Optional[SocInterface],
        Optional[int],
        Optional[int],
        Optional[int],
    ]
]:
    file_type = None
    soc = None
    auto_start = None
    auto_skip = None
    auto_length = None

    # auto-detection - stage 1 - common file types
    data = peek(file, size=512)
    if data:
        for name, patterns in FILE_TYPES.items():
            if all(
                data[offset : offset + len(pattern)] == pattern
                for offset, pattern in patterns
            ):
                file_type = name
                break

    if file_type:
        return file_type, None, None, None, None, None

    # auto-detection - stage 2 - checking using SocInterface
    file_size = stat(file.name).st_size
    if family is None:
        # check all families
        for f in Family.get_all():
            if f.name is None:
                continue
            try:
                soc = SocInterface.get(f)
                tpl = soc.flash_get_file_type(file, length=file_size)
            except NotImplementedError:
                tpl = None
            if tpl:
                file_type, auto_start, auto_skip, auto_length = tpl
            if file_type:
                family = f
                break
    else:
        # check the specified family only
        try:
            soc = SocInterface.get(family)
            tpl = soc.flash_get_file_type(file, length=file_size)
        except NotImplementedError:
            tpl = None
        if tpl:
            file_type, auto_start, auto_skip, auto_length = tpl

    return file_type, family, soc, auto_start, auto_skip, auto_length


@click.group(help="Flashing tool - reading/writing")
def cli():
    pass


@cli.command(short_help="Read flash contents")
@click.argument("family", type=FamilyParamType(by_parent=True))
@click.argument("file", type=File("wb"))
@click.option(
    "-d",
    "--device",
    help="Target device port (default: auto detect)",
    type=str,
)
@click.option(
    "-b",
    "--baudrate",
    help="UART baud rate (default: auto choose)",
    type=int,
)
@click.option(
    "-s",
    "--start",
    help="Starting address to read from (default: 0)",
    type=AutoIntParamType(),
)
@click.option(
    "-l",
    "--length",
    help="Length to read, in bytes (default: entire flash)",
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
    help="Check hash/CRC of the read data (default: True)",
    default=True,
)
def read(
    family: Family,
    file: FileIO,
    device: str,
    baudrate: int,
    start: int,
    length: int,
    timeout: float,
    check: bool,
):
    """
    Read flash contents to a file.

    By default, read the entire flash chip, starting at offset 0x0.

    When not specified (-d), the first UART port is used. The baud rate (-b)
    is chosen automatically, depending on the chip capabilities.

    \b
    Arguments:
      FAMILY    Chip family name/code
      FILE      Output file name
    """
    device = device or find_serial_port()
    if not device:
        return
    time_start = time()
    soc = SocInterface.get(family)
    soc.set_uart_params(port=device, baud=baudrate, link_timeout=timeout)

    start = start or 0
    length = length or soc.flash_get_size()

    graph(1, f"Reading {sizeof(length)} from '{family.description}' to '{file.name}'")
    for chunk in soc.flash_read_raw(start, length, verify=check):
        file.write(chunk)

    duration = time() - time_start
    graph(1, f"Finished in {duration:.3f} s")


@cli.command()
@click.argument("file", type=File("rb"))
@click.option(
    "-d",
    "--device",
    help="Target device port (default: auto detect)",
    type=str,
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
def write(
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
    device = device or find_serial_port()
    if not device:
        return
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
    graph(0, f"Writing '{file.name}' ({file_type}) to '{family.description}'")
    if family and not soc:
        soc = SocInterface.get(family)
    if not family:
        fatal("Unknown error in parameter processing logic")
        return
    soc.set_uart_params(port=device, baud=baudrate, link_timeout=timeout)

    if ctx:
        graph(1, ctx.fw_name, ctx.fw_version, "@", ctx.build_date, "->", ctx.board_name)
        soc.flash_write_uf2(ctx)
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
        soc.flash_write_raw(start, length, data=file, verify=check)

    duration = time() - time_start
    graph(1, f"Finished in {duration:.3f} s")


@cli.command(name="file", short_help="Detect file type")
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
    help="Amount of bytes to skip from **input file** (default: based on file type)",
    type=AutoIntParamType(),
)
def file_cmd(
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
    file_type, family, _, start, skip, length = get_file_type(family, file)
    info(f"{file.name}: {file_type or 'Unrecognized'}")
    debug(f"\tfamily={family}")
    debug(f"\tstart={start}")
    debug(f"\tskip={skip}")
    debug(f"\tlength={length}")

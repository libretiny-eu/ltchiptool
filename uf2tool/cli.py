# Copyright (c) Kuba Szczodrzyński 2022-07-29.

import logging
from logging import debug, warning
from os import makedirs
from os.path import join
from shutil import SameFileError, copyfile
from time import time
from typing import IO, Optional, Tuple

import click

from ltchiptool import Board
from ltchiptool.models import BoardParamType
from ltchiptool.util.misc import sizeof
from uf2tool.models import UF2, Image, ImageParamType, UploadContext
from uf2tool.models.enums import OTAScheme, OTASchemeParamType
from uf2tool.writer import UF2Writer


@click.group(help="Work with UF2 files")
def cli():
    pass


@cli.command(help="Create an UF2 file from binary inputs")
@click.option(
    "-o",
    "--output",
    help="Output .uf2 binary (can be specified multiple times)",
    type=str,
    multiple=True,
)
@click.option(
    "-b",
    "--board",
    help="Board name/code/JSON path",
    required=True,
    type=BoardParamType(),
)
@click.option("-L", "--lt-version", help="LibreTiny core version")
@click.option("-F", "--fw", help="Firmware name:version")
@click.option(
    "-d",
    "--date",
    help="Build date (Unix, default now)",
    type=int,
    default=time(),
)
@click.option("--legacy", help="Add legacy UF2 tags", is_flag=True)
@click.argument("IMAGES", nargs=-1, type=ImageParamType())
def write(
    output: Tuple[str],
    board: Board,
    lt_version: str,
    fw: str,
    date: int,
    legacy: bool,
    images: Tuple[Image],
):
    if not output:
        output = ("out.uf2",)

    family = board.family
    if not family.is_chip:
        raise ValueError(
            f"Family {family} is not a Chip Family - it can't be used here"
        )

    out_file = open(output[0], "wb")
    writer = UF2Writer(out_file, family, legacy)
    writer.set_board(board)
    if lt_version:
        writer.set_version(lt_version)
    if fw:
        writer.set_firmware(fw)
    writer.set_date(date)
    writer.write(images)
    out_file.close()

    for copy in output[1:]:
        debug(f"Copying UF2 as {copy}")
        try:
            copyfile(output[0], copy)
        except SameFileError:
            pass


@cli.command(help="Print info about UF2 file")
@click.argument("file", type=click.File("rb"))
def info(file: IO[bytes]):
    uf2 = UF2(file)
    uf2.read()
    uf2.dump()
    ctx = UploadContext(uf2)
    if not ctx.part_table:
        return
    logging.info("Partition table:")
    for part in ctx.part_table.partitions:
        logging.info(
            f" - {part.name}: "
            f"0x{part.offset:06X}+0x{part.length:X} "
            f"({sizeof(part.length)})"
        )


@cli.command(help="Dump UF2 contents")
@click.argument("file", type=click.File("rb"))
@click.option("-o", "--output", type=click.Path(file_okay=False), default=".")
@click.option("-s", "--scheme", type=OTASchemeParamType(), default=None, multiple=True)
def dump(file: IO[bytes], output: str, scheme: Optional[OTAScheme]):
    uf2 = UF2(file)
    uf2.read()
    ctx = UploadContext(uf2)
    makedirs(output, exist_ok=True)

    scheme_map = {
        OTAScheme.DEVICE_SINGLE: "device",
        OTAScheme.DEVICE_DUAL_1: "device1",
        OTAScheme.DEVICE_DUAL_2: "device2",
        OTAScheme.FLASHER_SINGLE: "flasher",
        OTAScheme.FLASHER_DUAL_1: "flasher1",
        OTAScheme.FLASHER_DUAL_2: "flasher2",
    }
    schemes = scheme or OTAScheme

    written = False
    for scheme in schemes:
        prefix = f"uf2dump_{uf2.family.code}_{scheme_map[scheme]}"
        ctx.seq = 0
        for offset, data in ctx.collect_data(scheme).items():
            path = f"{prefix}_0x{offset:06X}.bin"
            logging.info(f"Writing to {path}")
            with open(join(output, path), "wb") as f:
                f.write(data.read())
                written = True
    if not written:
        warning(
            f"No data found for the specified OTA scheme(s): "
            + ", ".join(scheme.name for scheme in schemes)
        )


@cli.command(
    context_settings=dict(
        ignore_unknown_options=True,
    ),
    hidden=True,
    deprecated=True,
    no_args_is_help=True,
)
@click.argument("_", nargs=-1)
def upload(*_, **__):
    """

    This command was removed in v2.0.0.
    Please use 'ltchiptool flash write' instead.
    """
    raise NotImplementedError(upload.__doc__)

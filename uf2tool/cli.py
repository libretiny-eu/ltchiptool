# Copyright (c) Kuba Szczodrzyński 2022-07-29.

import logging
from os import makedirs
from os.path import join
from time import time
from typing import IO, Tuple

import click

from ltchiptool import Family
from ltchiptool.models import FamilyParamType
from uf2tool.models import UF2, Input, InputParamType, UploadContext
from uf2tool.writer import UF2Writer


@click.group(help="Work with UF2 files")
def cli():
    pass


@cli.command(help="Create an UF2 file from binary inputs")
@click.option(
    "-o",
    "--output",
    help="Output .uf2 binary",
    type=click.File("wb"),
    default="out.uf2",
)
@click.option(
    "-f", "--family", help="Family name", required=True, type=FamilyParamType()
)
@click.option("-b", "--board", help="Board name/code")
@click.option("-v", "--version", help="LibreTuya core version")
@click.option("-F", "--fw", help="Firmware name:version")
@click.option(
    "-d", "--date", help="Build date (Unix, default now)", type=int, default=time()
)
@click.argument("INPUTS", nargs=-1, type=InputParamType())
def write(
    output: IO[bytes],
    family: Family,
    board: str,
    version: str,
    fw: str,
    date: int,
    inputs: Tuple[Input],
):
    writer = UF2Writer(output, family)
    if board:
        writer.set_board(board)
    if version:
        writer.set_version(version)
    if fw:
        writer.set_firmware(fw)
    writer.set_date(date)
    writer.write(inputs)


@cli.command(help="Print info about UF2 file")
@click.argument("file", type=click.File("rb"))
def info(file: IO[bytes]):
    uf2 = UF2(file)
    uf2.read()
    uf2.dump()


@cli.command(help="Dump UF2 contents")
@click.argument("file", type=click.File("rb"))
@click.option("-o", "--output", type=click.Path(file_okay=False), default=".")
def dump(file: IO[bytes], output: str):
    uf2 = UF2(file)
    uf2.read()
    ctx = UploadContext(uf2)
    makedirs(output, exist_ok=True)

    ota_idxs = []
    if ctx.has_ota1:
        ota_idxs.append(1)
    if ctx.has_ota2:
        ota_idxs.append(2)

    prefix = f"image_{ctx.board_name}_{ctx.uf2.family.code}"

    for ota_idx in ota_idxs:
        ctx.seq = 0
        for offset, data in ctx.collect(ota_idx).items():
            path = f"{prefix}_ota{ota_idx}_0x{offset:X}.bin"
            logging.info(f"Writing to {path}")
            with open(join(output, path), "wb") as f:
                f.write(data.read())


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

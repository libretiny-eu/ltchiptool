# Copyright (c) Kuba Szczodrzyński 2022-07-29.

from io import SEEK_SET, FileIO
from os import makedirs
from os.path import join
from time import time
from typing import Tuple

import click

from ltchiptool import Family, SocInterface
from ltchiptool.models import FamilyParamType
from ltchiptool.util import unpack_obj
from uf2tool.models import UF2, Input, InputParamType, UploadContext
from uf2tool.upload import ESPHomeUploader
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
    output: FileIO,
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
def info(file: FileIO):
    uf2 = UF2(file)
    uf2.read()
    uf2.dump()


@cli.command(help="Dump UF2 contents")
@click.argument("file", type=click.File("rb"))
@click.option("-o", "--output", type=click.Path(file_okay=False), default=".")
def dump(file: FileIO, output: str):
    uf2 = UF2(file)
    uf2.read()
    ctx = UploadContext(uf2)
    makedirs(output, exist_ok=True)

    ota_idxs = []
    if ctx.has_ota1:
        ota_idxs.append(1)
    if ctx.has_ota2:
        ota_idxs.append(2)

    prefix = f"image_{ctx.board_name}_{ctx.board.family.code}"

    for ota_idx in ota_idxs:
        ctx.seq = 0
        for offset, data in ctx.collect(ota_idx).items():
            path = f"{prefix}_ota{ota_idx}_0x{offset:X}.bin"
            print(f"Writing to {path}")
            with open(join(output, path), "wb") as f:
                f.write(data.read())


@cli.group(help="Upload UF2 file to IoT device")
@click.argument("file", type=click.File("rb"))
@click.pass_context
def upload(ctx, file: FileIO):
    uf2 = UF2(file)
    uf2.read(block_tags=False)
    context = UploadContext(uf2)
    print(
        f"|-- {context.fw_name} {context.fw_version} @ {context.build_date} -> {context.board_name}"
    )
    ctx.obj["file"] = file
    ctx.obj["start"] = time()
    ctx.obj["uf2"] = uf2
    ctx.obj["ctx"] = context
    ctx.obj["board"] = context.board
    ctx.obj["family"] = context.board.family
    ctx.obj["soc"] = SocInterface.get(context.board.family)


@upload.command("uart", help="Upload using UART protocol")
@click.argument("PORT")
@click.option("-b", "--baud", help="Baudrate (board default)", type=int)
@click.option(
    "-t", "--timeout", help="Timeout (transmission, linking, etc.)", type=float
)
@unpack_obj
def upload_uart(soc: SocInterface, start: float, **kwargs):
    print("|-- Using UART")
    soc.upload_uart(**kwargs)
    duration = time() - start
    print(f"|-- Finished in {duration:.3f} s")


@upload.command("openocd", help="Upload with OpenOCD")
def upload_openocd():
    raise NotImplementedError()


@upload.command("esphome", help="Upload via ESPHome OTA")
@click.argument("HOST")
@click.option("-P", "--port", help="OTA port", default=8892, type=int)
@click.option("-p", "--password", help="OTA password", default=None)
@click.option("-v", "--verbose", help="Print debugging info", is_flag=True)
@unpack_obj
def upload_esphome(
    uf2: UF2,
    file: FileIO,
    host: str,
    port: int,
    password: str,
    verbose: bool,
    start: float,
    **kwargs,
):
    file.seek(0, SEEK_SET)
    print(f"|-- Using ESPHome OTA ({host}:{port})")
    esphome = ESPHomeUploader(
        file=file,
        md5=uf2.md5.digest(),
        host=host,
        port=port,
        password=password,
        debug=verbose,
    )
    esphome.upload()
    duration = time() - start
    print(f"|-- Finished in {duration:.3f} s")

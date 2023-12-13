# Copyright (c) Kuba Szczodrzyński 2022-07-29.

import os
from logging import DEBUG, INFO, exception

import click
from click import Context
from serial import Serial

from ltchiptool.util.cli import get_multi_command_class
from ltchiptool.util.logging import VERBOSE, LoggingHandler, log_setup_click_bars
from ltchiptool.util.ltim import LTIM
from ltchiptool.util.lvm import LVM
from ltchiptool.util.streams import LoggingStreamHook

COMMANDS = {
    # compile commands
    "elf2bin": "ltchiptool/commands/compile/elf2bin.py",
    "link2bin": "ltchiptool/commands/compile/link2bin.py",
    "uf2": "uf2tool/cli.py",
    # flash commands
    "flash": "ltchiptool/commands/flash/__main__.py",
    # plugin commands
    "plugin": "ltchiptool/commands/plugin/run.py",
    "plugins": "ltchiptool/commands/plugin/manage.py",
    # other commands
    "gui": "ltchiptool/gui/__main__.py",
    "list": "ltchiptool/commands/list.py",
    "soc": "ltchiptool/commands/soc.py",
}

VERBOSITY_LEVEL = {
    0: INFO,
    1: DEBUG,
    2: VERBOSE,
}


@click.command(
    cls=get_multi_command_class(COMMANDS),
    help="Universal flashing and binary manipulation tool for IoT chips",
    context_settings=dict(help_option_names=["-h", "--help"]),
)
@click.option(
    "-v",
    "--verbose",
    help="Output debugging messages (repeat to output more)",
    count=True,
)
@click.option(
    "-T",
    "--traceback",
    help="Print complete exception traceback",
    is_flag=True,
)
@click.option(
    "-t",
    "--timed",
    help="Prepend log lines with timing info",
    is_flag=True,
)
@click.option(
    "-r",
    "--raw-log",
    help="Output logging messages with no additional styling",
    is_flag=True,
)
@click.option(
    "-i",
    "--indent",
    help="Indent log messages using graph lines",
    type=int,
    default=0,
)
@click.option(
    "-s",
    "--dump-serial",
    help="Dump transmitted Serial data",
    is_flag=True,
)
@click.option(
    "-L",
    "--libretiny-path",
    help="Set LibreTiny platform path",
    type=click.Path(exists=True, dir_okay=True),
)
@click.version_option(
    LTIM.get_version_full(),
    "-V",
    "--version",
    message="ltchiptool %(version)s",
)
@click.pass_context
def cli_entrypoint(
    ctx: Context,
    verbose: int,
    traceback: bool,
    timed: bool,
    raw_log: bool,
    indent: int,
    dump_serial: bool,
    libretiny_path: str,
):
    ctx.ensure_object(dict)
    if verbose == 0 and "LTCHIPTOOL_VERBOSE" in os.environ:
        verbose = int(os.environ["LTCHIPTOOL_VERBOSE"])
    logger = LoggingHandler.get()
    logger.level = VERBOSITY_LEVEL[min(verbose, 2)]
    logger.timed = timed
    logger.raw = raw_log
    logger.indent = indent
    logger.full_traceback = traceback
    log_setup_click_bars()
    LoggingStreamHook.set_registered(Serial, dump_serial)
    if libretiny_path:
        LVM.add_path(libretiny_path)


def cli():
    try:
        cli_entrypoint()
    except Exception as e:
        exception(None, exc_info=e)
        exit(1)


if __name__ == "__main__":
    cli()

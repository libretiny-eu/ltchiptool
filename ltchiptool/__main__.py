# Copyright (c) Kuba Szczodrzyński 2022-07-29.

import os
from logging import DEBUG, INFO

import click
from click import Context
from serial import Serial

from ltchiptool.util.cli import get_multi_command_class
from ltchiptool.util.logging import VERBOSE, LoggingHandler, log_setup_click_bars
from ltchiptool.util.streams import LoggingStreamHook

from .version import get_version

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
@click.version_option(
    get_version(),
    "-V",
    "--version",
    message="ltchiptool v%(version)s",
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


def cli():
    try:
        cli_entrypoint()
    except Exception as e:
        LoggingHandler.get().emit_exception(e)
        exit(1)


if __name__ == "__main__":
    cli()

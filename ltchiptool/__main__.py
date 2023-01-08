# Copyright (c) Kuba Szczodrzyński 2022-07-29.

from logging import DEBUG, INFO

import click
from click import Context

from ltchiptool.util import VERBOSE, LoggingHandler, get_multi_command_class, log_setup

from .version import get_version

COMMANDS = {
    "dump": "ltchiptool/commands/dumptool.py",
    "elf2bin": "ltchiptool/commands/elf2bin.py",
    "flash": "ltchiptool/commands/flash/__main__.py",
    "gui": "ltchiptool/gui/__main__.py",
    "link2bin": "ltchiptool/commands/link2bin.py",
    "list": "ltchiptool/commands/list.py",
    "soc": "ltchiptool/commands/soc.py",
    "uf2": "uf2tool/cli.py",
}

FULL_TRACEBACK: bool = False
VERBOSITY_LEVEL = {
    0: INFO,
    1: DEBUG,
    2: VERBOSE,
}


@click.command(
    cls=get_multi_command_class(COMMANDS),
    help="Tools for working with LT-supported IoT chips",
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
):
    global FULL_TRACEBACK
    FULL_TRACEBACK = traceback
    ctx.ensure_object(dict)
    log_setup(
        level=VERBOSITY_LEVEL[min(verbose, 2)],
        handler=LoggingHandler(timed=timed, raw=raw_log, indent=indent),
    )


def cli():
    try:
        cli_entrypoint()
    except Exception as e:
        LoggingHandler.INSTANCE.emit_exception(e, FULL_TRACEBACK)
        exit(1)


if __name__ == "__main__":
    cli()

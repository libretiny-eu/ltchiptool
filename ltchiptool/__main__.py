# Copyright (c) Kuba Szczodrzyński 2022-07-29.

from logging import ERROR, error

import click
from click import Context

from ltchiptool.util import get_multi_command_class, graph, log_setup

from .version import get_version

COMMANDS = {
    "dump": "ltchiptool/commands/dumptool.py",
    "elf2bin": "ltchiptool/commands/elf2bin.py",
    "flash": "ltchiptool/commands/flash/__main__.py",
    "link2bin": "ltchiptool/commands/link2bin.py",
    "list": "ltchiptool/commands/list.py",
    "soc": "ltchiptool/commands/soc.py",
    "uf2": "uf2tool/cli.py",
}

FULL_TRACEBACK: bool = False


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
    log_setup(verbosity=verbose, timed=timed, raw=raw_log, indent=indent)


def tb_echo(tb):
    filename = tb.tb_frame.f_code.co_filename
    name = tb.tb_frame.f_code.co_name
    line = tb.tb_lineno
    graph(1, f'File "{filename}", line {line}, in {name}', loglevel=ERROR)


def cli():
    try:
        cli_entrypoint()
    except Exception as e:
        error(f"{type(e).__name__}: {e}")
        tb = e.__traceback__
        while tb.tb_next:
            if FULL_TRACEBACK:
                tb_echo(tb)
            tb = tb.tb_next
        tb_echo(tb)
        exit(1)


if __name__ == "__main__":
    cli()

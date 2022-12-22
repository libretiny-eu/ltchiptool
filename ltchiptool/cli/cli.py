# Copyright (c) Kuba Szczodrzyński 2022-07-29.

import click
from click import Context

from ..util import log_setup
from ..version import get_version
from .util import get_multi_command_class

COMMANDS = {
    "dump": "ltchiptool/cli/dumptool.py",
    "elf2bin": "ltchiptool/cli/elf2bin.py",
    "link2bin": "ltchiptool/cli/link2bin.py",
    "list": "ltchiptool/cli/list.py",
    "soc": "ltchiptool/cli/soc.py",
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
@click.version_option(
    get_version(),
    "--version",
    "-V",
    message="ltchiptool v%(version)s",
)
@click.pass_context
def cli(
    ctx: Context,
    verbose: int,
    traceback: bool,
    timed: bool,
):
    global FULL_TRACEBACK
    FULL_TRACEBACK = traceback
    ctx.ensure_object(dict)
    log_setup(verbosity=verbose, timed=timed)


def tb_echo(tb):
    filename = tb.tb_frame.f_code.co_filename
    name = tb.tb_frame.f_code.co_name
    line = tb.tb_lineno
    click.secho(f' - File "{filename}", line {line}, in {name}', fg="red")


def main():
    try:
        cli()
    except Exception as e:
        click.secho(f"ERROR: {type(e).__name__}: {e}", fg="red")
        tb = e.__traceback__
        while tb.tb_next:
            if FULL_TRACEBACK:
                tb_echo(tb)
            tb = tb.tb_next
        tb_echo(tb)
        exit(1)

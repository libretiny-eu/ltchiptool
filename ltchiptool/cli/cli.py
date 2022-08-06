# Copyright (c) Kuba Szczodrzyński 2022-07-29.

from os.path import dirname, join
from typing import List, Optional

import click
from click import Command, Context, MultiCommand

from ..version import get_version

COMMANDS = {
    "dump": "ltchiptool/cli/dumptool.py",
    "elf2bin": "ltchiptool/cli/elf2bin.py",
    "link2bin": "ltchiptool/cli/link2bin.py",
    "list": "ltchiptool/cli/list.py",
    "uf2": "uf2tool/cli.py",
}

FULL_TRACEBACK: bool = False


class ChipToolCLI(MultiCommand):
    def list_commands(self, ctx: Context) -> List[str]:
        ctx.ensure_object(dict)
        return ["link2bin", "elf2bin", "uf2", "soc", "dump", "list"]

    def get_command(self, ctx: Context, cmd_name: str) -> Optional[Command]:
        if cmd_name not in COMMANDS:
            return None
        ns = {}
        fn = join(dirname(__file__), "..", "..", COMMANDS[cmd_name])
        with open(fn) as f:
            code = compile(f.read(), fn, "exec")
            eval(code, ns, ns)
        return ns["cli"]


@click.command(
    cls=ChipToolCLI,
    help="Tools for working with LT-supported IoT chips",
    context_settings=dict(help_option_names=["-h", "--help"]),
)
@click.option("--traceback", help="Print complete exception traceback", is_flag=True)
@click.version_option(
    get_version(), "--version", "-V", message="ltchiptool v%(version)s"
)
@click.pass_context
def cli(ctx: Context, traceback: bool):
    global FULL_TRACEBACK
    FULL_TRACEBACK = traceback
    ctx.ensure_object(dict)


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

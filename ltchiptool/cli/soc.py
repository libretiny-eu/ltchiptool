#  Copyright (c) Kuba Szczodrzyński 2022-10-5.

import click

from .util import get_multi_command_class

COMMANDS = {
    "bkpackager": "ltchiptool/soc/bk72xx/bkpackager.py",
}


@click.command(
    cls=get_multi_command_class(COMMANDS),
    help="Run SoC-specific tools",
)
def cli():
    pass

#  Copyright (c) Kuba Szczodrzyński 2022-12-26.

import click

from ltchiptool.util.cli import get_multi_command_class

COMMANDS = {
    "file": "ltchiptool/commands/flash/file.py",
    "read": "ltchiptool/commands/flash/read.py",
    "write": "ltchiptool/commands/flash/write.py",
}


@click.command(
    cls=get_multi_command_class(COMMANDS),
    help="Flashing tool - reading/writing",
)
def cli():
    pass


if __name__ == "__main__":
    cli()

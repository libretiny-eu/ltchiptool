#  Copyright (c) Kuba Szczodrzyński 2023-5-19.

from typing import Dict, List, Optional

import click
from click import Command, Context, MultiCommand

from ltchiptool.util.lpm import LPM


def get_commands() -> Dict[str, Command]:
    lpm = LPM.get()
    commands = {}
    for plugin in lpm.plugins:
        if not plugin.has_cli:
            continue
        commands.update(plugin.build_cli())
    return commands


class PluginCLI(MultiCommand):
    def list_commands(self, ctx: Context) -> List[str]:
        return list(get_commands().keys())

    def get_command(self, ctx: Context, cmd_name: str) -> Optional[Command]:
        return get_commands().get(cmd_name, None)


@click.command(
    cls=PluginCLI,
    short_help="Run plugin commands",
)
def cli():
    """
    Run commands exported from installed (enabled) plugins.

    Each plugin may export multiple commands, or it may not export any.

    See 'ltchiptool plugins list' for a list of installed plugins.
    """


if __name__ == "__main__":
    cli()

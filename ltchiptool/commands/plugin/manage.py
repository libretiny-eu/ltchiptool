#  Copyright (c) Kuba Szczodrzyński 2023-5-19.

import click
from prettytable import PrettyTable

from ltchiptool.util.lpm import LPM


@click.group(help="List & manage plugins")
def cli():
    pass


@cli.command(name="list", help="List installed plugins")
def list_():
    lpm = LPM.get()
    if not lpm.plugins:
        print("No plugins are installed")
        return
    table = PrettyTable()
    table.field_names = [
        "Name",
        "Version",
        "Enabled",
        "Description",
        "Type",
        "Module",
    ]
    table.align = "l"

    for name, plugin in lpm.plugins.items():
        if not plugin:
            table.add_row([name, "-", "No", "-", "-", name])
            continue
        table.add_row(
            [
                plugin.title,
                plugin.version,
                "Yes",
                plugin.description or "-",
                "CLI + GUI"
                if plugin.has_cli and plugin.has_gui
                else "CLI"
                if plugin.has_cli
                else "GUI"
                if plugin.has_gui
                else "?",
                type(plugin).__module__ + "." + type(plugin).__name__,
            ]
        )
    click.echo_via_pager(table.get_string())


if __name__ == "__main__":
    cli()

#  Copyright (c) Kuba Szczodrzyński 2023-5-19.

from logging import info, warning
from typing import List, Optional, Tuple

import click
from prettytable import PrettyTable

from ltchiptool.util.lpm import LPM
from ltctplugin.base import PluginBase


@click.group(help="List & manage plugins")
def cli():
    pass


def _format_type(plugin: PluginBase) -> str:
    return (
        "CLI + GUI"
        if plugin.has_cli and plugin.has_gui
        else "CLI"
        if plugin.has_cli
        else "GUI"
        if plugin.has_gui
        else "?"
    )


def _find_plugin(query: str) -> Tuple[str, Optional[PluginBase]]:
    lpm = LPM.get()
    query = query.lower()
    found = None
    found_partial = None
    for name, plugin in lpm.plugins.items():
        if found:
            continue
        keys = [
            name,
            plugin and plugin.title,
            plugin and plugin.distribution and plugin.distribution.name,
            plugin and plugin.namespace,
        ]
        for key in keys:
            if not key:
                continue
            if query == key.lower():
                found = name, plugin
                break
            if query in key.lower():
                found_partial = name, plugin
    return found or found_partial or (None, None)


@cli.command(name="list", help="List installed plugins")
def list_():
    lpm = LPM.get()
    if not lpm.plugins:
        print("No plugins are installed")
        return
    table = PrettyTable(align="l")
    table.field_names = [
        "Title",
        "Version",
        "Enabled",
        "Description",
        "Type",
    ]

    for name in sorted(lpm.plugins.keys()):
        plugin = lpm.plugins[name]
        if not plugin:
            table.add_row([name, "-", "No", "-", "-"])
            continue
        table.add_row(
            [
                plugin.title,
                plugin.version,
                "Yes",
                plugin.description or "-",
                _format_type(plugin),
            ]
        )
    click.echo_via_pager(table.get_string())


@cli.command(name="info", short_help="Show info about installed plugins")
@click.argument("QUERY", nargs=-1, required=True)
def info_(query: List[str]):
    """
    Show info about an installed plugin.

    Searches by plugin name, its distribution and namespace.
    If not found, also by parts of these names.

    \b
    Arguments:
      QUERY      Plugin name to search for
    """
    for q in query:
        name, plugin = _find_plugin(q)

        if not name:
            warning(f"No plugin found by query: {q}")
            return
        if not plugin:
            info(f"Plugin {name} is not enabled")
            return

        table = PrettyTable(align="l", header=False)
        table.add_row(["Title", plugin.title])
        table.add_row(["Version", plugin.version])
        table.add_row(["Description", plugin.description or "-"])
        table.add_row(["Author", plugin.author or "-"])
        table.add_row(["License", plugin.license or "-"])
        table.add_row(["Type", _format_type(plugin)])
        table.add_row(
            ["Distribution", plugin.distribution and plugin.distribution.name or "?"]
        )
        table.add_row(["Namespace", plugin.namespace])
        table.add_row(["Module", plugin.module])
        print(table.get_string())


if __name__ == "__main__":
    cli()

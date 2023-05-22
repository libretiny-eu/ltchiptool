#  Copyright (c) Kuba Szczodrzyński 2023-5-19.

from logging import info, warning
from typing import List, Optional

import click
from prettytable import PrettyTable

from ltchiptool.util.lpm import LPM
from ltctplugin.base import PluginBase


@click.group(help="List & manage plugins")
def cli():
    pass


def _find_plugin(query: str) -> Optional[PluginBase]:
    lpm = LPM.get()
    query = query.lower()
    found = None
    found_partial = None
    for plugin in lpm.plugins:
        if found:
            continue
        keys = [
            plugin.title,
            plugin.distribution.name,
            plugin.namespace,
        ]
        for key in keys:
            if not key:
                continue
            if query == key.lower():
                found = plugin
                break
            if query in key.lower():
                found_partial = plugin
    return found or found_partial


@cli.command(name="list", help="List installed plugins")
def list_():
    lpm = LPM.get()
    if not lpm.plugins:
        info("No plugins are installed")
        return
    table = PrettyTable(align="l")
    table.field_names = [
        "Title",
        "Version",
        "Enabled",
        "Description",
        "Type",
    ]

    for plugin in sorted(lpm.plugins, key=lambda p: p.title.lower()):
        table.add_row(
            [
                plugin.title,
                plugin.version,
                "Yes",
                plugin.description or "-",
                plugin.type_text,
            ]
        )
    for name in sorted(lpm.disabled):
        table.add_row([name, "-", "No", "-", "-"])
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
        plugin = _find_plugin(q)

        if not plugin:
            warning(f"Plugin is not installed or not enabled: {q}")
            return

        table = PrettyTable(align="l", header=False)
        table.add_row(["Title", plugin.title])
        table.add_row(["Version", plugin.version])
        table.add_row(["Description", plugin.description or "-"])
        table.add_row(["Author", plugin.author or "-"])
        table.add_row(["License", plugin.license or "-"])
        table.add_row(["Type", plugin.type_text])
        table.add_row(["Distribution", plugin.distribution.name])
        table.add_row(["Namespace", plugin.namespace])
        table.add_row(["Module", plugin.module])
        print(table.get_string())


@cli.command(short_help="Search for installable plugins")
@click.argument("QUERY", required=False)
def search(query: str):
    lpm = LPM.get()
    results = lpm.search(query)
    if not results:
        warning(f"No plugins found by query: {query}")
        return

    table = PrettyTable(align="l")
    table.field_names = [
        "Distribution",
        "Installed",
        "Latest",
        "Description",
    ]
    for result in sorted(results, key=lambda r: r.distribution):
        update = " *" if result.installed and result.installed != result.latest else ""
        table.add_row(
            [
                result.distribution,
                result.installed or "-",
                (result.latest or "") + update,
                result.description,
            ]
        )
    click.echo_via_pager(table.get_string())


@cli.command(short_help="Install a plugin")
@click.argument("NAME")
def install(name: str):
    lpm = LPM.get()
    lpm.install(name)


if __name__ == "__main__":
    cli()

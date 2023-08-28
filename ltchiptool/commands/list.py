# Copyright (c) Kuba Szczodrzyński 2022-08-06.

from typing import List

import click
from prettytable import PrettyTable

from ltchiptool import Board, Family
from ltchiptool.util.misc import sizeof


@click.group(help="List boards, families, etc.")
def cli():
    pass


@cli.command(help="List boards")
def boards():
    table = PrettyTable()
    table.field_names = [
        "Name",
        "Code",
        "MCU / Flash / RAM",
        "Family name",
    ]
    table.align["Name"] = "l"
    table.align["Code"] = "l"
    board_names = Board.get_list()
    for name in board_names:
        board = Board(name)
        info = " / ".join(
            [
                board["build.mcu"].upper(),
                sizeof(board["upload.flash_size"]),
                sizeof(board["upload.maximum_ram_size"]),
            ]
        )
        table.add_row(
            [
                board.title,
                board.name,
                info,
                board.family.name,
            ]
        )
    click.echo_via_pager(table.get_string())


@cli.command(help="List families")
def families():
    table = PrettyTable()
    table.field_names = [
        "Title",
        "Name",
        "Code",
        "Short name / ID",
        "Supported?",
        "Arduino?",
        "SDK package",
    ]
    table.align = "l"

    def add_families(families: List[Family], level: int):
        indent = (" " + "|   " * (level - 1) + "+-- ") if level else ""
        for family in families:
            table.add_row(
                [
                    indent + family.description,
                    family.name,
                    family.code,
                    f"{family.short_name.upper()} / 0x{family.id:08X}"
                    if family.short_name and family.id
                    else "-",
                    "-" if not family.id else "Yes" if family.is_supported else "No",
                    "-"
                    if not family.id
                    else "Yes"
                    if family.is_supported and family.has_arduino_core
                    else "No",
                    family.target_package or "-",
                ]
            )
            add_families(family.children, level + 1)

    add_families(Family.get_all_root(), level=0)
    click.echo_via_pager(table.get_string())

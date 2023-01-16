# Copyright (c) Kuba Szczodrzyński 2022-08-06.

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
        "Title (parent)",
        "Name (parent)",
        "Code (parent)",
        "Short name / ID",
    ]
    table.align["Title (parent)"] = "l"
    for family in Family.get_all():
        table.add_row(
            [
                f"{family.description} ({family.parent_description})"
                if family.parent_description
                else family.description,
                f"{family.name} ({family.parent})"
                if family.parent
                else family.name
                if family.name
                else "-",
                f"{family.code} ({family.parent_code})"
                if family.parent_code
                else family.code
                if family.code
                else "-",
                f"{family.short_name.upper()} / 0x{family.id:08X}",
            ]
        )
    click.echo_via_pager(table.get_string())

#  Copyright (c) Kuba Szczodrzyński 2023-12-7.

from logging import info
from time import time

import click
from prettytable import PrettyTable

from ltchiptool import Family, SocInterface
from ltchiptool.models import FamilyParamType
from ltchiptool.util.cli import DevicePortParamType
from ltchiptool.util.flash import FlashConnection
from ltchiptool.util.logging import graph

from ._utils import flash_link_interactive


@click.command(short_help="Get chip info")
@click.argument("family", type=FamilyParamType())
@click.option(
    "-d",
    "--device",
    help="Target device port (default: auto detect)",
    type=DevicePortParamType(),
    default=(),
)
@click.option(
    "-t",
    "--timeout",
    help="Chip connection timeout in seconds (default: 20.0)",
    type=float,
    default=None,
)
def cli(
    family: Family,
    device: str,
    timeout: float,
):
    """
    Read information about the connected chip.

    When not specified (-d), the first UART port is used.

    \b
    Arguments:
      FAMILY    Chip family name/code
    """
    time_start = time()
    soc = SocInterface.get(family)
    soc.flash_set_connection(FlashConnection(device, None))
    flash_link_interactive(soc, timeout)

    graph(0, f"Reading chip info...")

    info(f"Chip: {soc.flash_get_chip_info_string()}")

    chip_info = soc.flash_get_chip_info()
    table = PrettyTable()
    table.field_names = ["Name", "Value"]
    table.align = "l"
    for key, value in chip_info:
        table.add_row([key, value])

    for line in table.get_string().splitlines():
        info(line)

    duration = time() - time_start
    graph(1, f"Finished in {duration:.3f} s")

#  Copyright (c) Kuba Szczodrzyński 2022-12-23.

from logging import debug
from typing import List

from prettytable import PrettyTable

from ltchiptool import SocInterface
from ltchiptool.util.logging import LoggingHandler, graph


def _format_flash_guide(soc: SocInterface) -> List[str]:
    guide = []
    dash_line = "-" * 6
    empty_line = " " * 6
    for item in soc.flash_get_guide():
        if isinstance(item, str):
            if guide:
                guide.append(" ")
            guide += item.splitlines()
        elif isinstance(item, list):
            table = PrettyTable()
            left, right = item[0]
            left = left.rjust(6)
            right = right.ljust(6)
            table.field_names = [left, "", right]
            table.align[left] = "r"
            table.align[right] = "l"
            for left, right in item[1:]:
                table.add_row([left, dash_line if left and right else "", right])
            if guide:
                guide.append("")
            for line in table.get_string().splitlines():
                line = line[1:-1]
                line = line.replace(f"-+-{dash_line}-+-", f"-+ {empty_line} +-")
                guide.append(f"    {line}")
    return guide


def flash_link_interactive(
    soc: SocInterface,
    port: str,
    baud: int,
    link_timeout: float,
):
    for stage in range(4):
        debug(f"Linking: stage {stage}")
        if stage == 0:
            # use timeout of 1.0s to check if already linked
            soc.set_uart_params(port=port, baud=baud, link_timeout=2.0)
        elif stage == 1:
            # try hardware GPIO reset
            soc.flash_hw_reset()
        elif stage == 2:
            # guide the user to connect the chip properly, or reset it manually
            soc.set_uart_params(port=port, baud=baud, link_timeout=link_timeout or 20.0)
            for line in _format_flash_guide(soc):
                LoggingHandler.get().emit_string("I", line, color="bright_blue")
        else:
            # give up after link_timeout
            raise TimeoutError("Timeout while linking with the chip")

        try:
            if stage == 0:
                # print once, but after setting port and baud
                graph(
                    0,
                    f"Connecting to '{soc.family.description}' "
                    f"on {soc.port} @ {soc.baud}",
                )
            soc.flash_disconnect()
            soc.flash_connect()
            break
        except TimeoutError:
            stage += 1

    # successfully linked
    chip_info = soc.flash_get_chip_info_string()
    graph(1, f"Success! Chip info: {chip_info}")

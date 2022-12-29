#  Copyright (c) Kuba Szczodrzyński 2022-12-23.

from io import FileIO
from logging import debug
from os import stat
from typing import List, Optional, Tuple

from prettytable import PrettyTable

from ltchiptool import Family, SocInterface
from ltchiptool.util import LoggingHandler, graph, peek

FILE_TYPES = {
    "UF2": [
        (0x000, b"UF2\x0A"),
        (0x004, b"\x57\x51\x5D\x9E"),
        (0x1FC, b"\x30\x6F\xB1\x0A"),
    ],
    "ELF": [
        (0x00, b"\x7FELF"),
    ],
    "Tuya UG": [
        (0x00, b"\x55\xAA\x55\xAA"),
        (0x1C, b"\xAA\x55\xAA\x55"),
    ],
}


def get_file_type(
    family: Optional[Family],
    file: FileIO,
) -> Optional[
    Tuple[
        str,
        Optional[Family],
        Optional[SocInterface],
        Optional[int],
        Optional[int],
        Optional[int],
    ]
]:
    file_type = None
    soc = None
    auto_offset = None
    auto_skip = None
    auto_length = None

    # auto-detection - stage 1 - common file types
    data = peek(file, size=512)
    if data:
        for name, patterns in FILE_TYPES.items():
            if all(
                data[offset : offset + len(pattern)] == pattern
                for offset, pattern in patterns
            ):
                file_type = name
                break

    if file_type:
        return file_type, None, None, None, None, None

    # auto-detection - stage 2 - checking using SocInterface
    file_size = stat(file.name).st_size
    if family is None:
        # check all families
        for f in Family.get_all():
            if f.name is None:
                continue
            try:
                soc = SocInterface.get(f)
                tpl = soc.detect_file_type(file, length=file_size)
            except NotImplementedError:
                tpl = None
            if tpl:
                file_type, auto_offset, auto_skip, auto_length = tpl
            if file_type:
                family = f
                break
    else:
        # check the specified family only
        try:
            soc = SocInterface.get(family)
            tpl = soc.detect_file_type(file, length=file_size)
        except NotImplementedError:
            tpl = None
        if tpl:
            file_type, auto_offset, auto_skip, auto_length = tpl

    return file_type, family, soc, auto_offset, auto_skip, auto_length


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
                LoggingHandler.INSTANCE.emit_string("I", line, color="bright_blue")
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

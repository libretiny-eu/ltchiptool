#  Copyright (c) Kuba Szczodrzyński 2023-1-15.

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

from prettytable import PrettyTable

# compatibility
# noinspection PyUnresolvedReferences
from .streams import ClickProgressCallback

__compat__ = ClickProgressCallback


class FlashOp(Enum):
    WRITE = "write"
    READ = "read"
    READ_ROM = "read_rom"
    READ_EFUSE = "read_efuse"
    READ_INFO = "read_info"


class FlashMemoryType(Enum):
    FLASH = "Flash"
    ROM = "ROM"
    EFUSE = "eFuse"


@dataclass
class FlashConnection:
    port: str
    baudrate: Optional[int] = None
    link_baudrate: Optional[int] = None
    timeout: Optional[float] = None
    link_timeout: float = 20.0
    linked: bool = False

    def fill_baudrate(self, baudrate: int, link_baudrate: int = None) -> None:
        if link_baudrate is None:
            link_baudrate = baudrate
        self.link_baudrate = self.link_baudrate or link_baudrate
        self.baudrate = self.baudrate or baudrate or self.link_baudrate


@dataclass
class FlashFeatures:
    can_write: bool = True
    can_read: bool = True
    can_read_rom: bool = True
    can_read_efuse: bool = True
    can_read_info: bool = True


def format_flash_guide(soc) -> List[str]:
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

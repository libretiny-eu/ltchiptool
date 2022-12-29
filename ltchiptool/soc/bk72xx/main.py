# Copyright (c) Kuba Szczodrzyński 2022-07-29.

from abc import ABC
from logging import info

from ltchiptool import Family
from ltchiptool.soc import SocInterfaceCommon

from .elf2bin import BK72XXElf2Bin
from .flash import BK72XXFlash


class BK72XXMain(
    BK72XXElf2Bin,
    BK72XXFlash,
    SocInterfaceCommon,
    ABC,
):
    def __init__(self, family: Family) -> None:
        super().__init__()
        self.family = family

    def hello(self):
        info("Hello from BK72xx")

    @property
    def elf_has_dual_ota(self) -> bool:
        return False

# Copyright (c) Kuba Szczodrzyński 2022-07-29.

from abc import ABC
from logging import info

from ltchiptool import Family
from ltchiptool.soc import SocInterfaceCommon

from .binary import AmebaZBinary
from .flash import AmebaZFlash


class AmebaZMain(
    AmebaZBinary,
    AmebaZFlash,
    SocInterfaceCommon,
    ABC,
):
    def __init__(self, family: Family) -> None:
        super().__init__()
        self.family = family

    def hello(self):
        info("Hello from AmebaZ")

    @property
    def elf_has_dual_ota(self) -> bool:
        return True

#  Copyright (c) Kuba Szczodrzyński 2022-12-28.

from abc import ABC
from logging import info

from ltchiptool import Family
from ltchiptool.soc import SocInterfaceCommon

from .flash import AmebaZ2Flash


class AmebaZ2Main(
    AmebaZ2Flash,
    SocInterfaceCommon,
    ABC,
):
    def __init__(self, family: Family) -> None:
        super().__init__()
        self.family = family

    def hello(self):
        info("Hello from AmebaZ2")

    @property
    def elf_has_dual_ota(self) -> bool:
        return True

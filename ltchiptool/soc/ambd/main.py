# Copyright (c) Bl00d-B0b 2026-08-06.

from abc import ABC
from logging import info
from typing import Optional

from ltchiptool import Family
from ltchiptool.models import OTAType
from ltchiptool.soc import SocInterfaceCommon

from .binary import AmebaDBinary
from .flash import AmebaDFlash


class AmebaDMain(
    AmebaDBinary,
    AmebaDFlash,
    SocInterfaceCommon,
    ABC,
):
    def __init__(self, family: Family) -> None:
        super().__init__()
        self.family = family

    def hello(self):
        info("Hello from AmebaD")

    @property
    def ota_type(self) -> Optional[OTAType]:
        return OTAType.DUAL

    @property
    def ota_supports_format_1(self) -> bool:
        return True

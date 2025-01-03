# Copyright (c) Etienne Le Cousin 2025-01-02.

from abc import ABC
from logging import info
from typing import Optional

from ltchiptool import Family
from ltchiptool.models import OTAType
from ltchiptool.soc import SocInterfaceCommon

from .binary import LN882xBinary
from .flash import LN882xFlash


class LN882xMain(
    LN882xBinary,
    LN882xFlash,
    SocInterfaceCommon,
    ABC,
):
    def __init__(self, family: Family) -> None:
        super().__init__()
        self.family = family

    def hello(self):
        info("Hello from LN882x")

    @property
    def ota_type(self) -> Optional[OTAType]:
        return OTAType.SINGLE

    @property
    def ota_supports_format_1(self) -> bool:
        return True

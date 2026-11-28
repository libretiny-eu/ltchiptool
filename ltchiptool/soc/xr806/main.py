#  Copyright (c) 2026 bavci1988.

from abc import ABC
from logging import info
from typing import Optional

from ltchiptool import Family
from ltchiptool.models import OTAType
from ltchiptool.soc import SocInterfaceCommon

from .binary import XR806Binary
from .flash import XR806Flash


class XR806Main(
    XR806Binary,
    XR806Flash,
    SocInterfaceCommon,
    ABC,
):
    def __init__(self, family: Family) -> None:
        super().__init__()
        self.family = family

    def hello(self):
        info("Hello from XR806")

    @property
    def ota_type(self) -> Optional[OTAType]:
        return OTAType.SINGLE

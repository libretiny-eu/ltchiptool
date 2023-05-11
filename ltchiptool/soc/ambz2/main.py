#  Copyright (c) Kuba Szczodrzyński 2022-12-28.

from abc import ABC
from logging import info
from typing import Optional

from ltchiptool import Family
from ltchiptool.models import OTAType
from ltchiptool.soc import SocInterfaceCommon

from .binary import AmebaZ2Binary
from .flash import AmebaZ2Flash


class AmebaZ2Main(
    AmebaZ2Binary,
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
    def ota_type(self) -> Optional[OTAType]:
        return OTAType.DUAL

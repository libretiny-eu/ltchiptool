# Copyright (c) Kuba Szczodrzyński 2022-07-29.

from abc import ABC
from logging import info
from typing import Optional

from ltchiptool import Family
from ltchiptool.models import OTAType
from ltchiptool.soc import SocInterfaceCommon

from .binary import BK72XXBinary
from .flash import BK72XXFlash


class BK72XXMain(
    BK72XXBinary,
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
    def ota_type(self) -> Optional[OTAType]:
        return OTAType.SINGLE

    @property
    def ota_supports_format_1(self) -> bool:
        return True

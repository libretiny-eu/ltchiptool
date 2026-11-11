# Copyright (c) Andrew Rankin 2026-06-16.

from abc import ABC
from logging import info
from typing import Optional

from ltchiptool import Family
from ltchiptool.models import OTAType
from ltchiptool.soc import SocInterfaceCommon


class EFM32GG11Main(
    SocInterfaceCommon,
    ABC,
):
    def __init__(self, family: Family) -> None:
        super().__init__()
        self.family = family

    def hello(self):
        info("Hello from EFM32GG11")

    @property
    def ota_type(self) -> Optional[OTAType]:
        # Jump-based A/B dual-bank: ota1 @ 0x008000, ota2 @ 0x100000 (each
        # 0x0F0000). The running app stages the update into the inactive bank;
        # `uf2tool` emits DEVICE_DUAL_1 -> ota1 and DEVICE_DUAL_2 -> ota2, with a
        # binpatch carrying bank B's deltas against bank A.
        return OTAType.DUAL

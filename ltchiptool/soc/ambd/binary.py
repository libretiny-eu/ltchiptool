# Copyright (c) Bl00d-B0b 2026-08-06.

from abc import ABC

from ltchiptool import SocInterface

from .util.models import (
    AMBD_BOOT_ADDRESS,
    AMBD_KM4_XIP_ADDRESS,
    SectionHeader,
    pack_section,
)


class AmebaDBinary(SocInterface, ABC):
    """AmebaD image handling.

    Images: km4_boot_all.bin (boot XIP+RAM) and km0_km4_image2.bin (KM0 image2 ||
    KM4 image2, 32-byte prepend headers, plain-concatenated with security off).
    KM0 and the boot images ship prebuilt; elf2bin packages only the KM4 image2.
    """

    # The LibreTiny family builder (builder/family/realtek-ambd.py) packs the
    # OTA image from the linked ELF, so elf2bin/link2bin are not routed here
    # yet; the header primitives live in util/models.py.

    def elf2bin(self, input: str, ota_idx: int) -> dict:
        raise NotImplementedError(
            "AmebaD images are packed by the LibreTiny family builder"
        )

    def link2bin(self, input: str, ota_idx: int) -> dict:
        raise NotImplementedError(
            "AmebaD images are packed by the LibreTiny family builder"
        )

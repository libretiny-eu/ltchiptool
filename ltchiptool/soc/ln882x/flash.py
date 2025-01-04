# Copyright (c) Etienne Le Cousin 2025-01-02.

import logging
import struct
from abc import ABC
from binascii import crc32
from logging import DEBUG, debug, warning
from typing import IO, Generator, List, Optional, Tuple, Union

from ltchiptool import SocInterface
from ltchiptool.util.flash import FlashConnection, FlashFeatures, FlashMemoryType
from ltchiptool.util.intbin import gen2bytes, inttole32
from ltchiptool.util.logging import VERBOSE, verbose
from ltchiptool.util.misc import sizeof
from ltchiptool.util.streams import ProgressCallback
from uf2tool import OTAScheme, UploadContext

LN882x_GUIDE = [
    "Connect UART1 of the LN882x to the USB-TTL adapter:",
    [
        ("PC", "LN882x"),
        ("RX", "TX1 (GPIOA2 / P2)"),
        ("TX", "RX1 (GPIOA3 / P3)"),
        ("", ""),
        ("GND", "GND"),
    ],
    "Using a good, stable 3.3V power supply is crucial. Most flashing issues\n"
    "are caused by either voltage drops during intensive flash operations,\n"
    "or bad/loose wires.",
    "The UART adapter's 3.3V power regulator is usually not enough. Instead,\n"
    "a regulated bench power supply, or a linear 1117-type regulator is recommended.",
    "To enter download mode, the chip has to be rebooted while the flashing program\n"
    "is trying to establish communication.\n"
    "In order to do that, you need to bridge CEN/BOOT pin (GPIOA9) to GND with a wire.",
]


class LN882xFlash(SocInterface, ABC):
    info: List[Tuple[str, str]] = None

    def flash_get_features(self) -> FlashFeatures:
        return FlashFeatures()

    def flash_get_guide(self) -> List[Union[str, list]]:
        return LN882X_GUIDE

    def flash_get_docs_url(self) -> Optional[str]:
        return "https://docs.libretiny.eu/link/flashing-ln882x"

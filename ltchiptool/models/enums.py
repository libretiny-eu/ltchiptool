#  Copyright (c) Kuba Szczodrzyński 2023-3-6.

from enum import Enum, auto


class OTAType(Enum):
    SINGLE = auto()
    DUAL = auto()
    FILE = auto()

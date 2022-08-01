# Copyright (c) Kuba Szczodrzyński 2022-06-10.

from enum import Enum, IntEnum
from typing import Generator, Tuple, Union


class DataType(Enum):
    BINARY = "BINARY"
    PADDING_SIZE = "PADDING_SIZE"
    RBL = "RBL"


DataTuple = Tuple[DataType, Union[bytes, int]]
DataUnion = Union[bytes, DataTuple]
DataGenerator = Generator[DataUnion, None, None]


class OTAEncryption(IntEnum):
    NONE = 0
    XOR = 1
    AES256 = 2


class OTACompression(IntEnum):
    NONE = 0
    GZIP = 1
    QUICKLZ = 2
    FASTLZ = 3

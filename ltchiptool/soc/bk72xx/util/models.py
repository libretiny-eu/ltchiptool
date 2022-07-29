# Copyright (c) Kuba Szczodrzyński 2022-06-10.

from enum import Enum, IntFlag
from typing import Generator, Tuple, Union


class DataType(Enum):
    BINARY = "BINARY"
    PADDING_SIZE = "PADDING_SIZE"
    RBL = "RBL"


DataTuple = Tuple[DataType, Union[bytes, int]]
DataUnion = Union[bytes, DataTuple]
DataGenerator = Generator[DataUnion, None, None]


class OTAAlgorithm(IntFlag):
    NONE = 0
    CRYPT_XOR = 1
    CRYPT_AES256 = 2
    COMPRESS_GZIP = 256
    COMPRESS_QUICKLZ = 512
    COMPRESS_FASTLZ = 768

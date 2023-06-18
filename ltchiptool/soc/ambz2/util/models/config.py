#  Copyright (c) Kuba Szczodrzyński 2023-1-21.

from dataclasses import dataclass
from typing import Dict, List

from ltchiptool.util.obj import str2enum

from .enums import ImageType, PartitionType, SectionType


@dataclass
class ImageConfig:
    @dataclass
    class Keys:
        decryption: bytes
        keyblock: Dict[str, bytes]
        hash_keys: Dict[str, bytes]
        user_keys: Dict[str, bytes]
        xip_sce_key: bytes
        xip_sce_iv: bytes

        # noinspection PyTypeChecker
        def __post_init__(self):
            self.decryption = bytes.fromhex(self.decryption)
            self.xip_sce_key = bytes.fromhex(self.xip_sce_key)
            self.xip_sce_iv = bytes.fromhex(self.xip_sce_iv)
            self.keyblock = {k: bytes.fromhex(v) for k, v in self.keyblock.items()}
            self.hash_keys = {k: bytes.fromhex(v) for k, v in self.hash_keys.items()}
            self.user_keys = {k: bytes.fromhex(v) for k, v in self.user_keys.items()}

    @dataclass
    class Section:
        name: str
        type: SectionType
        entry: str
        elf: List[str]
        is_boot: bool = False

        # noinspection PyTypeChecker
        def __post_init__(self):
            self.type = str2enum(SectionType, self.type)

    @dataclass
    class Image:
        type: ImageType
        sections: List["ImageConfig.Section"]

        # noinspection PyArgumentList,PyTypeChecker
        def __post_init__(self):
            self.type = str2enum(ImageType, self.type)
            self.sections = [ImageConfig.Section(**v) for v in self.sections]

    keys: Keys
    ptable: Dict[str, PartitionType]
    boot: Section
    fw: List[Image]

    # noinspection PyArgumentList,PyTypeChecker
    def __post_init__(self):
        self.keys = ImageConfig.Keys(**self.keys)
        self.ptable = {k: str2enum(PartitionType, v) for k, v in self.ptable.items()}
        self.boot = ImageConfig.Section(**self.boot)
        self.fw = [ImageConfig.Image(**v) for v in self.fw]

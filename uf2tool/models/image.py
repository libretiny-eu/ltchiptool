# Copyright (c) Kuba Szczodrzyński 2022-05-27.

from logging import debug
from typing import Dict, List, Optional, Tuple

import click

from .enums import ImageTarget, OTAScheme


class Image:
    offset: int = 0
    files: List[str]
    targets: Dict[ImageTarget, List[Tuple[str, int]]]
    schemes: Dict[OTAScheme, Optional[str]]
    part_info: bytes

    # fw1.bin,fw2.bin=device:xip1,xip2;flasher:xip1,xip2
    # bk7231_fw.crc=flasher:app
    # bk7231_ota.rbl=device:download
    def __init__(self, value: str) -> None:
        debug(f"Image input string: {value}")
        try:
            file, target = value.split("=")
            file, _, offset = file.partition("+")
            self.offset = int(offset or "0", 0)
            self.files = file.split(",")
            assert self.files
            targets = [target.split(":") for target in target.split(";")]
            targets = {ImageTarget(k): v.split(",") for k, v in targets}
            self.targets = targets
        except Exception:
            raise ValueError(
                "Incorrect input format - should be "
                "file[,file][+offset]=type:part[,part][;type:part[,part]]"
            )

        self.schemes = {
            OTAScheme.DEVICE_SINGLE: None,
            OTAScheme.DEVICE_DUAL_1: None,
            OTAScheme.DEVICE_DUAL_2: None,
            OTAScheme.FLASHER_SINGLE: None,
            OTAScheme.FLASHER_DUAL_1: None,
            OTAScheme.FLASHER_DUAL_2: None,
        }

        for target, parts in targets.items():
            if len(self.files) != len(parts):
                raise ValueError("Target partition count doesn't match file count")
            if len(self.files) not in [1, 2]:
                raise ValueError("Can only supply 1 or 2 input files")
            for i, part in enumerate(parts):
                scheme = 3 if target == ImageTarget.FLASHER else 0
                if len(parts) == 2:
                    scheme += 1 + i
                self.schemes[OTAScheme(scheme)] = part

        # there can be at most 6 partition names
        part_names = sorted(filter(None, set(self.schemes.values())))
        part_indexes = ""
        for scheme in OTAScheme:
            if not self.schemes[scheme]:
                part_indexes += "0"
            else:
                part_indexes += str(part_names.index(self.schemes[scheme]) + 1)
        assert len(part_indexes) == 6

        self.part_info = (
            bytes.fromhex(part_indexes) + "\x00".join(part_names).encode() + b"\x00"
        )

        debug(f"UF2 input file count: {len(self.files)}")
        debug(f"Partition offset: {self.offset}")
        for idx in OTAScheme:
            debug(f"Partition for {idx.name}: {self.schemes[idx]}")
        debug(f"Partition list tag: {self.part_info.hex()}")

    def read_file_1(self) -> bytes:
        with open(self.files[0], "rb") as f:
            return f.read()

    def read_file_2(self) -> Optional[bytes]:
        if len(self.files) < 2:
            return None
        with open(self.files[1], "rb") as f:
            return f.read()


class ImageParamType(click.ParamType):
    name = "image"

    def convert(self, value, param, ctx) -> Image:
        try:
            return Image(value)
        except ValueError as e:
            self.fail(e.args[0], param, ctx)

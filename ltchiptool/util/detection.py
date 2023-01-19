#  Copyright (c) Kuba Szczodrzyński 2023-1-14.

from dataclasses import dataclass
from enum import Enum
from os import SEEK_CUR, stat
from typing import IO, Optional

from ltchiptool import Board, Family, SocInterface
from uf2tool.models import UF2, Tag

from .fileio import peek

FILE_TYPES = {
    "UF2": [
        (0x000, b"UF2\x0A"),
        (0x004, b"\x57\x51\x5D\x9E"),
        (0x1FC, b"\x30\x6F\xB1\x0A"),
    ],
    "ELF": [
        (0x00, b"\x7FELF"),
    ],
    "Tuya UG": [
        (0x00, b"\x55\xAA\x55\xAA"),
        (0x1C, b"\xAA\x55\xAA\x55"),
    ],
}


@dataclass
class Detection:
    class Type(Enum):
        UNRECOGNIZED = "Unrecognized"
        RAW = "Raw"
        UNSUPPORTED = "Not flashable"
        UNSUPPORTED_HERE = "Not flashable with this family"
        UNSUPPORTED_UF2 = "UF2 (Unsupported)"
        VALID_UF2 = "UF2"
        VALID_NEED_OFFSET = "Valid (needs manual offset)"
        VALID = "Valid"

    name: str
    size: int
    type: Type
    file_type: Optional[str] = None

    offset: int = 0
    skip: int = 0
    length: int = 0

    family: Optional[Family] = None
    soc: Optional[SocInterface] = None
    uf2: Optional[UF2] = None

    def __post_init__(self):
        if not self.length:
            self.length = self.size - (self.skip or 0)

    @property
    def title(self) -> str:
        return self.file_type or self.type.value

    @property
    def is_flashable(self) -> bool:
        return self.type in [
            Detection.Type.RAW,
            Detection.Type.VALID_UF2,
            Detection.Type.VALID_NEED_OFFSET,
            Detection.Type.VALID,
        ]

    @property
    def is_uf2(self) -> bool:
        return self.type in [
            Detection.Type.UNSUPPORTED_UF2,
            Detection.Type.VALID_UF2,
        ]

    @property
    def need_offset(self) -> bool:
        return self.type == Detection.Type.VALID_NEED_OFFSET

    @staticmethod
    def make(
        type_name: str,
        offset: Optional[int],
        skip: int = 0,
        length: int = 0,
    ) -> "Detection":
        return Detection(
            name="",
            size=0,
            type=Detection.Type.VALID
            if offset is not None
            else Detection.Type.VALID_NEED_OFFSET,
            file_type=type_name,
            offset=offset or 0,
            skip=skip,
            length=length,
        )

    @staticmethod
    def make_unsupported(type_name: str) -> "Detection":
        return Detection(
            name="",
            size=0,
            type=Detection.Type.UNSUPPORTED_HERE,
            file_type=type_name,
        )

    @staticmethod
    def make_raw(file: IO[bytes]) -> "Detection":
        return Detection(
            name=file.name,
            size=stat(file.name).st_size,
            type=Detection.Type.RAW,
        )

    @staticmethod
    def perform(file: IO[bytes], family: Family = None) -> "Detection":
        return _detect_file(file, family)


def _detect_file(file: IO[bytes], family: Family = None) -> Detection:
    file_name = file.name
    file_size = stat(file_name).st_size - file.tell()

    wrap_type = None
    wrap_skip = None

    # auto-detection - stage 1 - common file types
    data = peek(file, size=512)
    file_type = None
    if data:
        for name, patterns in FILE_TYPES.items():
            if all(
                data[offset : offset + len(pattern)] == pattern
                for offset, pattern in patterns
            ):
                file_type = name
                break

    if file_type == "UF2":
        uf2 = UF2(file)
        uf2_type = Detection.Type.VALID_UF2
        try:
            uf2.read(block_tags=False)
            fw_name = uf2.tags.get(Tag.FIRMWARE, b"").decode()
            fw_version = uf2.tags.get(Tag.VERSION, b"").decode()
            board_name = uf2.tags.get(Tag.BOARD, b"").decode()
            if fw_name and fw_version:
                file_type = f"UF2 - {fw_name} {fw_version}"
            elif board_name:
                try:
                    board = Board(board_name)
                    file_type = f"UF2 - {board.title}"
                except FileNotFoundError:
                    file_type = f"UF2 - {board_name}"
            else:
                file_type = "UF2 - unknown board"
        except ValueError:
            uf2_type = Detection.Type.UNSUPPORTED_UF2
            file_type = "UF2 - unrecognized family"

        return Detection(
            name=file_name,
            size=file_size,
            type=uf2_type,
            file_type=file_type,
            family=uf2.family,
            uf2=uf2,
        )
    elif file_type == "Tuya UG":
        wrap_type = file_type
        wrap_skip = 0x20
        file_size -= 0x20
        file.seek(0x20, SEEK_CUR)
    elif file_type is not None:
        return Detection(
            name=file_name,
            size=file_size,
            type=Detection.Type.UNSUPPORTED,
            file_type=file_type,
        )

    # auto-detection - stage 2 - checking using SocInterface
    soc: Optional[SocInterface] = None
    detection: Optional[Detection] = None
    if family is None:
        # check all families
        for f in Family.get_all():
            if f.name is None:
                continue
            try:
                soc = SocInterface.get(f)
                detection = soc.detect_file_type(file, length=file_size)
            except NotImplementedError:
                detection = None
            if detection is not None:
                family = f
                break
    else:
        # check the specified family only
        try:
            soc = SocInterface.get(family)
            detection = soc.detect_file_type(file, length=file_size)
        except NotImplementedError:
            detection = None

    if detection is not None:
        detection.name = file_name
        detection.size = file_size
        detection.family = family
        detection.soc = soc
        if wrap_type and wrap_skip:
            detection.file_type = f"{wrap_type} > {detection.file_type}"
            detection.size += wrap_skip
            if detection.skip is not None:
                detection.skip += wrap_skip
        # update length if needed
        detection.__post_init__()
        return detection

    return Detection(
        name=file_name,
        size=file_size,
        type=Detection.Type.UNRECOGNIZED,
    )

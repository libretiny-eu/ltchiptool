#  Copyright (c) Kuba Szczodrzyński 2022-12-23.

from io import FileIO
from os import stat
from typing import Optional, Tuple

from ltchiptool import Family, SocInterface
from ltchiptool.util import peek

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


def get_file_type(
    family: Optional[Family],
    file: FileIO,
) -> Optional[
    Tuple[
        str,
        Optional[Family],
        Optional[SocInterface],
        Optional[int],
        Optional[int],
        Optional[int],
    ]
]:
    file_type = None
    soc = None
    auto_start = None
    auto_skip = None
    auto_length = None

    # auto-detection - stage 1 - common file types
    data = peek(file, size=512)
    if data:
        for name, patterns in FILE_TYPES.items():
            if all(
                data[offset : offset + len(pattern)] == pattern
                for offset, pattern in patterns
            ):
                file_type = name
                break

    if file_type:
        return file_type, None, None, None, None, None

    # auto-detection - stage 2 - checking using SocInterface
    file_size = stat(file.name).st_size
    if family is None:
        # check all families
        for f in Family.get_all():
            if f.name is None:
                continue
            try:
                soc = SocInterface.get(f)
                tpl = soc.flash_get_file_type(file, length=file_size)
            except NotImplementedError:
                tpl = None
            if tpl:
                file_type, auto_start, auto_skip, auto_length = tpl
            if file_type:
                family = f
                break
    else:
        # check the specified family only
        try:
            soc = SocInterface.get(family)
            tpl = soc.flash_get_file_type(file, length=file_size)
        except NotImplementedError:
            tpl = None
        if tpl:
            file_type, auto_start, auto_skip, auto_length = tpl

    return file_type, family, soc, auto_start, auto_skip, auto_length

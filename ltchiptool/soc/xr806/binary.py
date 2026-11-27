#  Copyright (c) 2026 bavci1988.

import struct
from abc import ABC
from typing import IO, Optional

from ltchiptool import SocInterface
from ltchiptool.util.detection import Detection
from ltchiptool.util.fileio import peek

AWIH_MAGIC = b"AWIH"
SECTION_ID_BOOT = 0xA5FF5A00
SECTION_ID_APP = 0xA5FE5A01


class XR806Binary(SocInterface, ABC):
    def detect_file_type(
        self,
        file: IO[bytes],
        length: int,
    ) -> Optional[Detection]:
        data = peek(file, size=64)
        if not data or data[0:4] != AWIH_MAGIC:
            return None
        section_id = struct.unpack_from("<I", data, 0x24)[0]
        # xr_system.img from the SDK starts with the bootloader section
        if section_id == SECTION_ID_BOOT:
            return Detection.make("XR806 System Image", offset=0)
        return Detection.make_unsupported("XR806 Section Image")

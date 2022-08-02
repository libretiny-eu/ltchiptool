# Copyright (c) Kuba Szczodrzyński 2022-06-02.

from datetime import datetime
from io import BytesIO
from typing import Dict, Optional, Tuple

from ltchiptool import Board
from ltchiptool.util.intbin import letoint
from uf2tool.binpatch import binpatch_apply

from .enums import Tag
from .uf2 import UF2


class UploadContext:
    uf2: UF2

    seq: int = 0

    part1: str = None
    part2: str = None

    has_ota1: bool
    has_ota2: bool

    _board: Board = None

    def __init__(self, uf2: UF2) -> None:
        self.uf2 = uf2
        self.has_ota1 = uf2.tags.get(Tag.LT_HAS_OTA1, None) == b"\x01"
        self.has_ota2 = uf2.tags.get(Tag.LT_HAS_OTA2, None) == b"\x01"

    @property
    def fw_name(self) -> str:
        return self.uf2.tags.get(Tag.FIRMWARE, b"").decode()

    @property
    def fw_version(self) -> str:
        return self.uf2.tags.get(Tag.VERSION, b"").decode()

    @property
    def lt_version(self) -> str:
        return self.uf2.tags.get(Tag.LT_VERSION, b"").decode()

    @property
    def board_name(self) -> str:
        return self.uf2.tags.get(Tag.BOARD, b"").decode()

    @property
    def board(self) -> Board:
        if not self._board:
            self._board = Board(self.board_name)
        return self._board

    @property
    def build_date(self) -> Optional[datetime]:
        if Tag.BUILD_DATE not in self.uf2.tags:
            return None
        return datetime.fromtimestamp(letoint(self.uf2.tags[Tag.BUILD_DATE]))

    @property
    def baudrate(self) -> int:
        return self.board["upload.speed"]

    def get_offset(self, part: str, offs: int) -> Optional[int]:
        (start, length, end) = self.board.region(part)
        if offs >= length:
            return None
        return start + offs

    def read(self, ota_idx: int = 1) -> Optional[Tuple[str, int, bytes]]:
        """Read next available data block for the specified OTA scheme.

        Returns:
            Tuple[str, int, bytes]: target partition, relative offset, data block
        """

        if ota_idx not in [1, 2]:
            raise ValueError(f"Invalid OTA index - {ota_idx}")

        if ota_idx == 1 and not self.has_ota1:
            raise ValueError(f"No data for OTA index - {ota_idx}")
        if ota_idx == 2 and not self.has_ota2:
            raise ValueError(f"No data for OTA index - {ota_idx}")

        for _ in range(self.seq, len(self.uf2.data)):
            block = self.uf2.data[self.seq]
            self.seq += 1

            part1 = block.tags.get(Tag.LT_PART_1, None)
            part2 = block.tags.get(Tag.LT_PART_2, None)

            if part1 is not None and part2 is not None:
                # decode empty tags too
                self.part1 = part1.decode()
                self.part2 = part2.decode()
            elif part1 or part2:
                raise ValueError(
                    f"Only one target partition specified - {part1} / {part2}"
                )

            if not block.data:
                continue

            part = None
            if ota_idx == 1:
                part = self.part1
            elif ota_idx == 2:
                part = self.part2
            if not part:
                continue

            # got data and target partition
            offs = block.address
            data = block.data

            if ota_idx == 2 and Tag.LT_BINPATCH in block.tags:
                binpatch = block.tags[Tag.LT_BINPATCH]
                data = bytearray(data)
                data = binpatch_apply(data, binpatch)
                data = bytes(data)

            return part, offs, data
        return None, 0, None

    def collect(self, ota_idx: int = 1) -> Optional[Dict[int, BytesIO]]:
        """Read all UF2 blocks. Gather continuous data parts into sections
        and their flashing offsets.

        Returns:
            Dict[int, BytesIO]: map of flash offsets to streams with data
        """

        out: Dict[int, BytesIO] = {}
        while True:
            ret = self.read(ota_idx)
            if not ret:
                return None
            (part, offs, data) = ret
            if not data:
                break
            offs = self.get_offset(part, offs)
            if offs is None:
                return None

            # find BytesIO in the dict
            for io_offs, io_data in out.items():
                if io_offs + len(io_data.getvalue()) == offs:
                    io_data.write(data)
                    offs = 0
                    break
            if offs == 0:
                continue

            # create BytesIO at specified offset
            io = BytesIO()
            io.write(data)
            out[offs] = io
        # rewind BytesIO back to start
        for io in out.values():
            io.seek(0)
        return out

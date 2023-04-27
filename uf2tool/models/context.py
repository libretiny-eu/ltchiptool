# Copyright (c) Kuba Szczodrzyński 2022-06-02.

from datetime import datetime
from io import BytesIO
from logging import error
from typing import Dict, Optional, Tuple

from ltchiptool import Board
from ltchiptool.util.intbin import letoint
from uf2tool.binpatch import binpatch_apply

from .enums import OTAScheme, Tag
from .partition import PartitionTable
from .uf2 import UF2


class UploadContext:
    uf2: UF2
    part: Optional[str] = None
    seq: int = 0
    part_table: PartitionTable = None
    _board: Board = None

    def __init__(self, uf2: UF2) -> None:
        self.uf2 = uf2
        if not uf2.data:
            raise ValueError("UF2 file is empty (or not loaded yet)")
        if Tag.OTA_FORMAT_2 not in uf2.tags:
            raise ValueError(
                "This UF2 is of legacy format and can't be read. "
                "Use ltchiptool v3.0.0 or older to read this package."
            )
        if Tag.FAL_PTABLE in uf2.tags:
            partition_table = uf2.tags[Tag.FAL_PTABLE]
            self.part_table = PartitionTable.unpack(
                partition_table,
                name_len=16,
                length=len(partition_table),
            )

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
        # TODO move this out of here
        return self.board["upload.speed"]

    def get_offset(self, part: str, offs: int) -> Optional[int]:
        if self.part_table:
            try:
                partition = next(
                    p for p in self.part_table.partitions if p.name == part
                )
            except StopIteration:
                raise ValueError(
                    f"Partition '{part}' not found in custom partition table"
                )
            start = partition.offset
            length = partition.length
        else:
            (start, length, _) = self.board.region(part)

        if offs >= length:
            error(f"Partition '{part}' rel. offset 0x{offs:X} larger than 0x{length:X}")
            return None
        return start + offs

    def read_next(self, scheme: OTAScheme) -> Optional[Tuple[str, int, bytes]]:
        """
        Read next available data block for the specified OTA scheme.

        Returns:
            Tuple[str, int, bytes]: target partition, relative offset, data block
        """

        for _ in range(self.seq, len(self.uf2.data)):
            block = self.uf2.data[self.seq]
            self.seq += 1

            part_info = block.tags.get(Tag.OTA_PART_INFO, None)
            if part_info is not None:
                self.parse_part_info(scheme, part_info)

            if not self.part or not block.data:
                continue

            # got data and target partition
            offs = block.address
            data = block.data

            if Tag.BINPATCH in block.tags and scheme.name.endswith("2"):
                binpatch = block.tags[Tag.BINPATCH]
                data = bytearray(data)
                data = binpatch_apply(data, binpatch)
                data = bytes(data)

            return self.part, offs, data
        return None

    def parse_part_info(self, scheme: OTAScheme, info: bytes) -> None:
        if len(info) < 3:
            raise ValueError("Invalid OTA_PART_INFO: too short")
        part_names = info[3:].split(b"\x00")
        part_names = [part.decode() for part in part_names if part]
        part_indexes = list(map(int, info[0:3].hex()))
        assert len(part_indexes) == 6
        self.part = None
        if not part_names:
            return
        index = part_indexes[scheme]
        if index == 0:
            return
        if index > len(part_names):
            raise ValueError("Invalid OTA_PART_INFO: missing partition name")
        self.part = part_names[index - 1]

    def collect_data(self, scheme: OTAScheme) -> Optional[Dict[int, BytesIO]]:
        """
        Read all UF2 blocks. Gather continuous data parts into sections
        and their flashing offsets.

        Returns:
            Dict[int, BytesIO]: map of flash offsets to streams with data
        """

        if not self.board_name:
            raise ValueError("This UF2 is not readable, since no board name is present")

        out: Dict[int, BytesIO] = {}
        while True:
            ret = self.read_next(scheme)
            if not ret:
                break
            (part, offs, data) = ret
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

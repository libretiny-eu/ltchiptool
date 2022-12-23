# Copyright (c) Kuba Szczodrzyński 2022-07-29.

from abc import ABC
from typing import BinaryIO, Dict, Generator, List, Optional

from ltchiptool import Board, Family
from ltchiptool.util import graph
from uf2tool import UploadContext


class SocInterface(ABC):
    board: Board = None
    port: str = None
    baud: int = None
    link_timeout: float = 20.0
    read_timeout: float = 1.0

    @classmethod
    def get(cls, family: Family) -> "SocInterface":
        # fmt: off
        if family.parent_code == "bk72xx":
            from .bk72xx import BK72XXMain
            return BK72XXMain()
        if family.code == "ambz":
            from .ambz import AmebaZMain
            return AmebaZMain()
        # fmt: on
        raise NotImplementedError(f"Unsupported family - {family.name}")

    #########################
    # Common helper methods #
    #########################

    def set_board(self, board: Board):
        self.board = board
        if board:
            self.baud = self.baud or board["upload.speed"] or 115200

    def set_uart_params(
        self,
        port: str,
        baud: int = None,
        link_timeout: float = None,
        read_timeout: float = None,
    ):
        self.port = port or self.port
        self.baud = baud or self.baud
        self.link_timeout = link_timeout or self.link_timeout
        self.read_timeout = read_timeout or self.read_timeout

    def print_protocol(self):
        graph(2, f"Connecting on {self.port} @ {self.baud}")

    #####################################################
    # Abstract methods - implemented by the SoC modules #
    #####################################################

    def hello(self):
        raise NotImplementedError()

    @property
    def elf_has_dual_ota(self) -> bool:
        raise NotImplementedError()

    ##################################
    # Linking - ELF and BIN building #
    ##################################

    def link2elf(
        self,
        ota1: str,
        ota2: str,
        args: List[str],
    ) -> List[str]:
        raise NotImplementedError()

    def elf2bin(
        self,
        input: str,
        ota_idx: int,
    ) -> Dict[str, Optional[int]]:
        raise NotImplementedError()

    def link2bin(
        self,
        ota1: str,
        ota2: str,
        args: List[str],
    ) -> Dict[str, Optional[int]]:
        raise NotImplementedError()

    #########################################################
    # Flashing - reading/writing raw files and UF2 packages #
    #########################################################

    def flash_read_raw(
        self,
        offset: int,
        length: int,
        use_rom: bool = False,
    ) -> Generator[bytes, None, None]:
        raise NotImplementedError()

    def flash_write_raw(
        self,
        offset: int,
        length: int,
        data: BinaryIO,
        verify: bool = True,
    ):
        raise NotImplementedError()

    def flash_write_uf2(
        self,
        ctx: UploadContext,
    ):
        raise NotImplementedError()

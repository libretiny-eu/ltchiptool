# Copyright (c) Kuba Szczodrzyński 2022-07-29.

from abc import ABC
from typing import Dict, Optional

from ltchiptool.models import Board
from uf2tool.models import UploadContext


class SocInterface(ABC):
    def hello(self):
        raise NotImplementedError()

    @property
    def elf_has_dual_ota(self) -> bool:
        raise NotImplementedError()

    def elf2bin(
        self, board: Board, input: str, ota_idx: int
    ) -> Dict[str, Optional[int]]:
        raise NotImplementedError()

    def upload_uart(self, ctx: UploadContext, port: str, baud: int = None, **kwargs):
        raise NotImplementedError()

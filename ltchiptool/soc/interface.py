# Copyright (c) Kuba Szczodrzyński 2022-07-29.

from abc import ABC
from typing import Dict, Optional

from ltchiptool import Board, Family
from uf2tool import UploadContext


class SocInterface(ABC):
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

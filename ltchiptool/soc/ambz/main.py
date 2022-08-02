# Copyright (c) Kuba Szczodrzyński 2022-07-29.

from typing import Dict, Optional

from ltchiptool import Board, SocInterface
from uf2tool import UploadContext

from .elf2bin import elf2bin
from .upload import upload


class AmebaZMain(SocInterface):
    def hello(self):
        print("Hello from AmebaZ")

    @property
    def elf_has_dual_ota(self) -> bool:
        return True

    def elf2bin(
        self, board: Board, input: str, ota_idx: int
    ) -> Dict[str, Optional[int]]:
        return elf2bin(board, input, ota_idx)

    def upload_uart(self, ctx: UploadContext, port: str, baud: int = None, **kwargs):
        upload(ctx, port, baud, **kwargs)

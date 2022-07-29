# Copyright (c) Kuba Szczodrzyński 2022-07-29.

from typing import Dict, Optional

from ltchiptool.models import Board
from ltchiptool.soc import SocInterface
from uf2tool.models import UploadContext

from .elf2bin import elf2bin
from .upload import upload


class AmebaZMain(SocInterface):
    def hello(self):
        print("Hello from AmebaZ")

    def elf2bin(
        self, board: Board, input: str, ota_idx: int
    ) -> Dict[str, Optional[int]]:
        return elf2bin(board, input, ota_idx)

    def upload_uart(self, ctx: UploadContext, port: str, baud: int = None, **kwargs):
        upload(ctx, port, baud, **kwargs)

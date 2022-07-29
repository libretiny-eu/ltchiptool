# Copyright (c) Kuba Szczodrzyński 2022-07-29.

from abc import ABC

from uf2tool.models import UploadContext


class SocInterface(ABC):
    def hello(self):
        raise NotImplementedError()

    def upload_uart(self, ctx: UploadContext, port: str, baud: int = None, **kwargs):
        raise NotImplementedError()

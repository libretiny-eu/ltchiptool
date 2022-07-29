# Copyright (c) Kuba Szczodrzyński 2022-07-29.

from ltchiptool.soc import SocInterface
from uf2tool.models import UploadContext

from .upload import upload


class AmebaZMain(SocInterface):
    def hello(self):
        print("Hello from AmebaZ")

    def upload_uart(self, ctx: UploadContext, port: str, baud: int = None, **kwargs):
        upload(ctx, port, baud, **kwargs)

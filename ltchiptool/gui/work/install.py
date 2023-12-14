#  Copyright (c) Kuba Szczodrzyński 2023-12-14.

from ltchiptool.util.ltim import LTIM

from .base import BaseThread


class InstallThread(BaseThread):
    def __init__(self, **kwargs):
        super().__init__()
        self.kwargs = kwargs

    def run_impl(self):
        LTIM.get().install(**self.kwargs)

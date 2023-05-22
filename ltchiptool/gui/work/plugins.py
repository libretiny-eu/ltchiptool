#  Copyright (c) Kuba Szczodrzyński 2023-5-22.

from ltchiptool.util.lpm import LPM

from .base import BaseThread


class PluginsThread(BaseThread):
    def __init__(
        self,
        scan: bool = False,
        search: bool = False,
        install: str = None,
    ):
        super().__init__()
        self.scan = scan
        self.search = search
        self.install = install
        self.success = False
        self.results: list[LPM.SearchResult] = []

    def run_impl(self):
        lpm = LPM.get()
        if self.scan:
            for plugin in lpm.plugins:
                _ = plugin.distribution
                _ = plugin.plugin_meta
        if self.search:
            self.results = lpm.search()
        if self.install:
            self.success = lpm.install(self.install)

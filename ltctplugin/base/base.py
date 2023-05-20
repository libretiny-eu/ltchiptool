#  Copyright (c) Kuba Szczodrzyński 2023-5-19.

import re
import sys
from abc import ABC
from functools import lru_cache
from os.path import isfile, join
from typing import Any, Dict, Optional

from importlib_metadata import Distribution, PackagePath, distributions, metadata

from ltchiptool.util.logging import LoggingHandler


class PluginBase(ABC):
    @property
    def entry_file(self) -> str:
        return sys.modules[self.__module__].__file__

    @property
    def is_site(self) -> bool:
        return "site-packages" in self.entry_file

    @lru_cache
    def get_distribution_meta(self) -> Optional[dict]:
        if self.is_site:
            file = self.entry_file.replace("\\", "/")
            file = file.partition("site-packages/")[2]
            path = PackagePath(file)
            for d in distributions():
                d: Distribution
                if path in d.files:
                    return d.metadata.json
        else:
            file = self.entry_file.partition("ltctplugin")[0]
            file = join(file, "pyproject.toml")
            if isfile(file):
                with open(file, "r", encoding="utf-8") as f:
                    text = f.read()
                meta = {}
                keys = [
                    ("name", "name"),
                    ("version", "version"),
                    ("description", "summary"),
                    ("authors", "author"),
                    ("license", "license"),
                ]
                for src, dst in keys:
                    value = re.search(rf"{src}\s?=\s?\"(.+?)\"", text)
                    if value:
                        meta[dst] = value.group(1)
                    else:
                        meta[dst] = None
                return meta
        return None

    @property
    @lru_cache
    def plugin_meta(self) -> dict:
        try:
            meta = self.get_distribution_meta()
        except Exception as e:
            LoggingHandler.get().emit_exception(e)
            meta = dict()
        return dict(
            title=meta.get("name", None) or type(self).__name__,
            description=meta.get("summary", None),
            version=meta.get("version", None) or "0.0.0",
            author=meta.get("author", None),
            license=meta.get("license", None),
        )

    @property
    def title(self) -> str:
        return self.plugin_meta["title"]

    @property
    def description(self) -> Optional[str]:
        return self.plugin_meta["description"]

    @property
    def version(self) -> str:
        return self.plugin_meta["version"]

    @property
    def author(self) -> Optional[str]:
        return self.plugin_meta["author"]

    @property
    def license(self) -> Optional[str]:
        return self.plugin_meta["license"]

    @property
    def has_cli(self) -> bool:
        return False

    @property
    def has_gui(self) -> bool:
        return False

    def build_cli(self, *args, **kwargs) -> Dict[str, Any]:
        return {}

    def build_gui(self, *args, **kwargs) -> Dict[str, Any]:
        return {}

    def unload(self) -> None:
        pass

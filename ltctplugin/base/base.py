#  Copyright (c) Kuba Szczodrzyński 2023-5-19.

import re
import site
import sys
from abc import ABC
from functools import lru_cache
from glob import glob
from os.path import basename, isdir, isfile, join
from pathlib import Path
from typing import Any, Dict, Optional

from importlib_metadata import Distribution, PackagePath, distributions

from ltchiptool.util.logging import LoggingHandler


class PluginBase(ABC):
    @property
    def entry_file(self) -> str:
        return sys.modules[self.__module__].__file__

    @property
    def namespace(self) -> str:
        return type(self).__module__.split(".")[1]

    @property
    def module(self) -> str:
        return type(self).__module__ + "." + type(self).__name__

    @property
    def is_site(self) -> bool:
        return "site-packages" in self.entry_file

    @property
    @lru_cache
    def distribution(self) -> Distribution:
        if self.is_site:
            file = self.entry_file.replace("\\", "/")
            file = file.partition("site-packages/")[2]
            path = PackagePath(file)
            for d in distributions():
                d: Distribution
                if path in d.files:
                    return d
        else:
            entry = Path(self.entry_file)
            for path in site.getsitepackages() + [site.getusersitepackages()]:
                for file in glob(join(path, "*.pth")):
                    with open(file, "r", encoding="utf-8") as f:
                        pth = f.read().strip()
                    if not isdir(pth):
                        continue
                    if entry.is_relative_to(pth):
                        name = basename(file).rpartition(".")[0]
                        return Distribution.from_name(name)
        raise ValueError(f"Distribution of plugin {self.namespace} not found")

    @property
    @lru_cache
    def _distribution_meta(self) -> Optional[dict]:
        if self.is_site:
            return self.distribution.metadata.json
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
                    value = re.search(rf"{src}\s?=\s?\[?\"(.+?)\"\]?", text)
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
            meta = self._distribution_meta
        except Exception as e:
            LoggingHandler.get().emit_exception(e)
            meta = dict()
        description: str = meta.get("summary", None)
        if description:
            description = description.replace("(ltchiptool plugin)", "").strip()
        return dict(
            title=meta.get("name", None) or self.namespace,
            description=description,
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
    def type_text(self) -> str:
        return (
            "CLI + GUI"
            if self.has_cli and self.has_gui
            else "CLI"
            if self.has_cli
            else "GUI"
            if self.has_gui
            else "?"
        )

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

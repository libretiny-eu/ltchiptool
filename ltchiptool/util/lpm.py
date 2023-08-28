#  Copyright (c) Kuba Szczodrzyński 2023-5-19.

import inspect
import re
import sys
from dataclasses import dataclass
from importlib import import_module
from logging import debug, error, info, warning
from os.path import join
from pkgutil import iter_modules
from typing import List, Optional, Set, Tuple

from click import get_app_dir

import ltctplugin
from ltchiptool.util.cli import run_subprocess
from ltchiptool.util.fileio import readjson, writejson
from ltchiptool.util.logging import LoggingHandler
from ltctplugin.base import PluginBase

PYPI_URL = "https://pypi.org/search/"


class LPM:
    INSTANCE: "LPM" = None
    plugins: List[PluginBase]
    disabled: Set[str]

    @dataclass
    class SearchResult:
        distribution: str
        description: str
        latest: str
        installed: str = None

    @staticmethod
    def get() -> "LPM":
        if LPM.INSTANCE:
            return LPM.INSTANCE
        LPM.INSTANCE = LPM()
        return LPM.INSTANCE

    def __init__(self) -> None:
        super().__init__()
        self.plugins = list()
        self.disabled = set()
        self.config_file = join(get_app_dir("ltchiptool"), "plugins.json")
        self.config_load()
        self.rescan()

    def config_load(self):
        config = readjson(self.config_file)
        if config:
            self.disabled = set(config.get("disabled", []))

    def config_save(self):
        config = dict(
            disabled=list(self.disabled),
        )
        writejson(self.config_file, config)

    def rescan(self) -> Tuple[Set[str], Set[str]]:
        prev = self.disabled.union(p.namespace for p in self.plugins)
        loaded = set(p.namespace for p in self.plugins)
        found = set(
            name for _, name, _ in iter_modules(ltctplugin.__path__) if name != "base"
        )
        if self.disabled - found:
            # remove non-existent disabled plugins
            self.disabled = found.intersection(self.disabled)
            self.config_save()
        # filter out disabled plugins
        found = set(name for name in found if name not in self.disabled)
        for namespace in loaded - found:
            # unload plugins
            for i, plugin in enumerate(self.plugins):
                if namespace == plugin.namespace:
                    self.plugins.pop(i)
                    plugin.unload()
                    del plugin
                    break
            debug(f"Unloaded '{namespace}'")
        for namespace in found - loaded:
            # load newly found plugins
            module = import_module(f"ltctplugin.{namespace}")
            entrypoint = getattr(module, "entrypoint", None)
            if not entrypoint:
                warning(f"Plugin '{namespace}' has no entrypoint!")
            try:
                plugin = entrypoint()
                self.plugins.append(plugin)
                debug(f"Loaded plugin '{namespace}'")
            except Exception as e:
                error(f"Couldn't load plugin '{namespace}', disabling!")
                LoggingHandler.get().emit_exception(e)
                self.disable(namespace, rescan=False)
        curr = self.disabled.union(p.namespace for p in self.plugins)
        return prev, curr

    def enable(self, namespace: str, rescan: bool = True) -> None:
        if namespace in self.disabled:
            self.disabled.remove(namespace)
            self.config_save()
            if rescan:
                self.rescan()

    def disable(self, namespace: str, rescan: bool = True) -> None:
        if namespace not in self.disabled:
            self.disabled.add(namespace)
            self.config_save()
            if rescan:
                self.rescan()

    def search(self, query: str = None) -> List[SearchResult]:
        try:
            import requests
        except (ModuleNotFoundError, ImportError):
            error("Module 'requests' not found - install it using pip install requests")
            return []

        out = []
        pkg_regex = r'<a class="package-snippet" .+?</a>'
        meta_regex = r'__(\w+?)">([^\s].+?)<'

        # fetch the search page
        query = query or "ltchiptool"
        info(f"Searching '{query}' on PyPI...")
        with requests.get(PYPI_URL, params=dict(q=query)) as r:
            html = r.text
            # go through all found packages
            for pkg in re.finditer(pkg_regex, html, re.DOTALL):
                meta = {}
                # parse metadata into the dict
                for match in re.finditer(meta_regex, pkg.group(0)):
                    meta[match.group(1)] = match.group(2)
                # check if all required keys were found
                if {"name", "description", "version"} - set(meta.keys()):
                    warning("Missing metadata")
                    warning(pkg.group(0))
                    continue
                # build the search result
                result = LPM.SearchResult(
                    distribution=meta["name"],
                    description=meta["description"],
                    latest=meta["version"],
                )
                # check if the package is a plugin
                if (
                    result.distribution.startswith("ltchiptool-")
                    or result.distribution.startswith("ltchiptool_")
                    or "ltchiptool plugin" in result.description
                ):
                    out.append(result)

        # check if any plugins are installed
        for result in out:
            for plugin in self.plugins:
                # try all loaded plugins
                if result.distribution == plugin.distribution.name:
                    result.installed = plugin.version
                    break
            # try installed packages as well
            if not result.installed:
                pass

        return out

    def install(self, distribution: str) -> bool:
        code = run_subprocess(
            sys.executable,
            "-m",
            "pip",
            "install",
            "--upgrade",
            distribution,
        )
        if code != 0:
            return False
        prev, curr = self.rescan()
        added = curr - prev
        if not added:
            warning("No new plugins were added!")
        else:
            info(f"Installed plugin {' '.join(added)}")
        return True

    def find_self(self) -> Optional[PluginBase]:
        self_namespace = None
        try:
            raise Exception
        except Exception:
            _, _, traceback = sys.exc_info()
            module = inspect.getmodule(traceback.tb_frame.f_back)
            self_namespace = module.__name__
            del traceback
            del module
        if not self_namespace or not self_namespace.startswith("ltctplugin."):
            return None

        for plugin in self.plugins:
            if self_namespace.startswith(f"ltctplugin.{plugin.namespace}"):
                return plugin
        return None

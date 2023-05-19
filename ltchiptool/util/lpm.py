#  Copyright (c) Kuba Szczodrzyński 2023-5-19.

from importlib import import_module
from logging import debug, error, warning
from os.path import join
from pkgutil import iter_modules
from typing import Dict, Optional, Set

from click import get_app_dir

import ltctplugin
from ltchiptool.util.fileio import readjson, writejson
from ltchiptool.util.logging import LoggingHandler
from ltctplugin.base import PluginBase


class LPM:
    INSTANCE: "LPM" = None
    plugins: Dict[str, Optional[PluginBase]]
    disabled: Set[str]

    @staticmethod
    def get() -> "LPM":
        if LPM.INSTANCE:
            return LPM.INSTANCE
        LPM.INSTANCE = LPM()
        return LPM.INSTANCE

    def __init__(self) -> None:
        super().__init__()
        self.plugins = {}
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

    def rescan(self) -> None:
        loaded = set(self.plugins.keys())
        found = set(
            name
            for _, name, _ in iter_modules(ltctplugin.__path__)
            if name not in self.disabled and name != "base"
        )
        for name in loaded - found:
            # unload plugins
            plugin = self.plugins.pop(name)
            plugin.unload()
            del plugin
            debug(f"Unloaded '{name}'")
        for name in found - loaded:
            # load newly found plugins
            module = import_module(f"ltctplugin.{name}")
            entrypoint = getattr(module, "entrypoint", None)
            if not entrypoint:
                warning(f"Plugin '{name}' has no entrypoint!")
            try:
                plugin = entrypoint()
                self.plugins[name] = plugin
                debug(f"Loaded plugin '{name}'")
            except Exception as e:
                error(f"Couldn't load plugin '{name}', disabling!")
                LoggingHandler.get().emit_exception(e)
                self.disable(name, rescan=False)

    def enable(self, name: str, rescan: bool = True) -> None:
        if name in self.disabled:
            self.disabled.remove(name)
            self.config_save()
            if rescan:
                self.rescan()

    def disable(self, name: str, rescan: bool = True) -> None:
        if name not in self.disabled:
            self.disabled.add(name)
            self.config_save()
            if rescan:
                self.rescan()

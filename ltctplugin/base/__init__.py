#  Copyright (c) Kuba Szczodrzyński 2023-5-19.

from .base import PluginBase

entrypoint = PluginBase

__all__ = [
    "PluginBase",
    "entrypoint",
]

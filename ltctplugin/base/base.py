#  Copyright (c) Kuba Szczodrzyński 2023-5-19.

from abc import ABC
from typing import Any, Dict, Optional


class PluginBase(ABC):
    @property
    def title(self) -> str:
        return "Base plugin"

    @property
    def description(self) -> Optional[str]:
        return None

    @property
    def version(self) -> str:
        return "0.0.0"

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

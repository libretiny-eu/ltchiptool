#  Copyright (c) Kuba Szczodrzyński 2023-12-13.

import os
import sys
from functools import lru_cache
from pathlib import Path
from typing import List, Optional, Tuple

import requests

from ltchiptool.util.cli import run_subprocess
from ltchiptool.util.streams import ClickProgressCallback
from ltchiptool.version import get_version

PYTHON_RELEASES = "https://www.python.org/api/v2/downloads/release/?pre_release=false&is_published=true&version=3"
PYTHON_RELEASE_FILE_FMT = (
    "https://www.python.org/api/v2/downloads/release_file/?release=%s&os=1"
)
PYTHON_GET_PIP = "https://bootstrap.pypa.io/get-pip.py"


# utilities to manage ltchiptool installation in different modes,
# fetch version information, find bundled resources, etc.


class LTIMBase:
    """ltchiptool installation manager"""

    INSTANCE: "LTIM" = None
    callback: ClickProgressCallback = None
    is_gui_entrypoint: bool = False

    @staticmethod
    def get() -> "LTIM":
        if LTIM.INSTANCE:
            return LTIM.INSTANCE
        LTIM.INSTANCE = LTIM()
        return LTIM.INSTANCE

    @staticmethod
    def is_windows() -> bool:
        return os.name == "nt"

    @staticmethod
    def is_linux() -> bool:
        return sys.platform == "linux"

    @staticmethod
    def is_macos() -> bool:
        return sys.platform == "darwin"

    @property
    def is_bundled(self) -> bool:
        return getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")

    def get_resource(self, name: str) -> Path:
        if self.is_bundled:
            return Path(sys._MEIPASS) / name
        return Path(__file__).parents[2] / name

    def get_gui_resource(self, name: str) -> Path:
        if self.is_bundled:
            return Path(sys._MEIPASS) / name
        return Path(__file__).parents[1] / "gui" / "res" / name

    @staticmethod
    @lru_cache
    def get_version() -> Optional[str]:
        return get_version()

    @staticmethod
    def get_version_full() -> Optional[str]:
        tool_version = LTIM.get_version()
        if not tool_version:
            return None
        tool_version = "v" + tool_version
        if "site-packages" not in __file__ and not hasattr(sys, "_MEIPASS"):
            tool_version += " (dev)"
        return tool_version

    def install(
        self,
        out_path: Path,
        shortcut: Optional[str],
        fta: List[str],
        add_path: bool,
    ) -> None:
        self.callback = ClickProgressCallback()

        out_path = out_path.expanduser().resolve()
        out_path.mkdir(parents=True, exist_ok=True)

        python_path, pythonw_path = self._install_python(out_path)

        self.callback.on_message("Downloading get-pip.py")
        get_pip_path = out_path / "get-pip.py"
        with requests.get(PYTHON_GET_PIP) as r:
            get_pip_path.write_bytes(r.content)

        opts = ["--prefer-binary", "--no-warn-script-location"]

        self.callback.on_message("Installing pip")
        return_code = run_subprocess(
            python_path,
            get_pip_path,
            *opts,
            cwd=out_path,
        )
        if return_code != 0:
            raise RuntimeError(f"{get_pip_path.name} returned {return_code}")

        self.callback.on_message("Checking pip installation")
        return_code = run_subprocess(
            python_path,
            "-m",
            "pip",
            "--version",
            cwd=out_path,
        )
        if return_code != 0:
            raise RuntimeError(f"pip --version returned {return_code}")

        self.callback.on_message("Installing ltchiptool with GUI extras")
        return_code = run_subprocess(
            python_path,
            "-m",
            "pip",
            "install",
            "ltchiptool[gui]",
            *opts,
            "--upgrade",
            cwd=out_path,
        )
        if return_code != 0:
            raise RuntimeError(f"pip install returned {return_code}")

        if shortcut:
            self._install_shortcut(out_path, public=shortcut == "public")
        if fta:
            self._install_fta(out_path, *fta)
        if add_path:
            self._install_path(out_path)

        self.callback.finish()

    def _install_python(self, out_path: Path) -> Tuple[Path, Path]: ...

    def _install_shortcut(self, out_path: Path, public: bool) -> None: ...

    def _install_fta(self, out_path: Path, *fta: str) -> None: ...

    def _install_path(self, out_path: Path) -> None: ...


if LTIMBase.is_windows():
    from .ltim_windows import LTIM

#  Copyright (c) Kuba Szczodrzyński 2023-12-13.

import platform
import sys
from functools import lru_cache
from io import BytesIO
from logging import DEBUG, info
from os.path import expandvars
from pathlib import Path
from subprocess import PIPE, Popen
from typing import Callable, Optional, Tuple
from zipfile import ZipFile

import requests
from semantic_version import SimpleSpec, Version

from ltchiptool.util.cli import run_subprocess
from ltchiptool.util.logging import LoggingHandler
from ltchiptool.version import get_version

PYTHON_RELEASES = "https://www.python.org/api/v2/downloads/release/?pre_release=false&is_published=true&version=3"
PYTHON_RELEASE_FILE_FMT = (
    "https://www.python.org/api/v2/downloads/release_file/?release=%s&os=1"
)
PYTHON_GET_PIP = "https://bootstrap.pypa.io/get-pip.py"


# utilities to manage ltchiptool installation in different modes,
# fetch version information, find bundled resources, etc.


class LTIM:
    """ltchiptool installation manager"""

    INSTANCE: "LTIM" = None
    on_message: Callable[[str], None] = None

    @staticmethod
    def get() -> "LTIM":
        if LTIM.INSTANCE:
            return LTIM.INSTANCE
        LTIM.INSTANCE = LTIM()
        return LTIM.INSTANCE

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
        return Path(__file__).parents[1] / "gui" / name

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

    def message(self, msg: str) -> None:
        info(msg)
        if self.on_message:
            self.on_message(msg)

    def install(self, out_path: Path) -> None:
        out_path = out_path.expanduser().resolve()
        out_path.mkdir(parents=True, exist_ok=True)

        python_path, pythonw_path = self._install_python_windows(out_path)

        self.on_message("Downloading get-pip.py...")
        get_pip_path = out_path / "get-pip.py"
        with requests.get(PYTHON_GET_PIP) as r:
            get_pip_path.write_bytes(r.content)

        opts = ["--prefer-binary", "--no-warn-script-location"]

        self.on_message("Installing pip...")
        return_code = run_subprocess(
            python_path,
            get_pip_path,
            *opts,
            cwd=out_path,
        )
        if return_code != 0:
            raise RuntimeError(f"{get_pip_path.name} returned {return_code}")

        self.on_message("Checking pip installation...")
        return_code = run_subprocess(
            python_path,
            "-m",
            "pip",
            "--version",
            cwd=out_path,
        )
        if return_code != 0:
            raise RuntimeError(f"pip --version returned {return_code}")

        self.on_message("Installing ltchiptool with GUI extras...")
        return_code = run_subprocess(
            python_path,
            "-m",
            "pip",
            "install",
            "ltchiptool[gui]",
            *opts,
            cwd=out_path,
        )
        if return_code != 0:
            raise RuntimeError(f"pip install returned {return_code}")

    def _install_python_windows(self, out_path: Path) -> Tuple[Path, Path]:
        version_spec = SimpleSpec("~3.11")

        self.on_message("Checking the latest Python version...")
        with requests.get(PYTHON_RELEASES) as r:
            releases = r.json()
            releases_map = [
                (Version.coerce(release["name"].partition(" ")[2]), release)
                for release in releases
            ]
            latest_version, latest_release = max(
                (
                    (version, release)
                    for (version, release) in releases_map
                    if version in version_spec
                ),
                key=lambda tpl: tpl[0],
            )
            latest_release_id = next(
                part
                for part in latest_release["resource_uri"].split("/")
                if part.isnumeric()
            )

        self.on_message(f"Will install Python {latest_version}")
        with requests.get(PYTHON_RELEASE_FILE_FMT % latest_release_id) as r:
            release_files = r.json()
            for release_file in release_files:
                release_url = release_file["url"]
                if (
                    "embed-" in release_url
                    and platform.machine().lower() in release_url
                ):
                    break
            else:
                raise RuntimeError("Couldn't find embeddable package URL")

        self.on_message(
            f"Downloading and extracting '{release_url}' to '{out_path}'..."
        )
        with requests.get(release_url) as r:
            with ZipFile(BytesIO(r.content)) as z:
                z.extractall(out_path)

        self.on_message("Checking installed executable...")
        python_path = out_path / "python.exe"
        pythonw_path = out_path / "pythonw.exe"
        p = Popen(
            args=[python_path, "--version"],
            stdout=PIPE,
        )
        version_name, _ = p.communicate()
        if p.returncode != 0:
            raise RuntimeError(f"{python_path.name} returned {p.returncode}")
        version_tuple = version_name.decode().partition(" ")[2].split(".")

        self.on_message("Enabling site-packages...")
        pth_path = out_path / ("python%s%s._pth" % tuple(version_tuple[:2]))
        if not pth_path.is_file():
            raise RuntimeError(f"Extraction failed, {pth_path.name} is not a file")
        pth = pth_path.read_text()
        pth = pth.replace("#import site", "import site")
        pth_path.write_text(pth)

        return python_path, pythonw_path


if __name__ == "__main__":
    LoggingHandler.get().level = DEBUG
    LTIM.get().install(out_path=Path(expandvars("%PROGRAMFILES%\\kuba2k2\\ltchiptool")))

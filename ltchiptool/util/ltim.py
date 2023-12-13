#  Copyright (c) Kuba Szczodrzyński 2023-12-13.

import platform
import sys
from functools import lru_cache
from io import BytesIO
from logging import DEBUG, info
from os.path import expandvars
from pathlib import Path
from subprocess import PIPE, Popen
from typing import Optional, Tuple
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

    @staticmethod
    def get() -> "LTIM":
        if LTIM.INSTANCE:
            return LTIM.INSTANCE
        LTIM.INSTANCE = LTIM()
        return LTIM.INSTANCE

    @staticmethod
    def get_resource(name: str) -> Path:
        pass

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

    def install(self, out_path: Path) -> None:
        out_path = out_path.expanduser().resolve()
        out_path.mkdir(parents=True, exist_ok=True)

        python_path, pythonw_path = self._install_python_windows(out_path)

        info("Downloading get-pip.py...")
        get_pip_path = out_path / "get-pip.py"
        with requests.get(PYTHON_GET_PIP) as r:
            get_pip_path.write_bytes(r.content)

        opts = ["--prefer-binary", "--no-warn-script-location"]

        info("Installing pip...")
        return_code = run_subprocess(
            python_path,
            get_pip_path,
            *opts,
            cwd=out_path,
        )
        if return_code != 0:
            raise RuntimeError(f"{get_pip_path.name} returned {return_code}")

        info("Checking pip installation...")
        return_code = run_subprocess(
            python_path,
            "-m",
            "pip",
            "--version",
            cwd=out_path,
        )
        if return_code != 0:
            raise RuntimeError(f"pip --version returned {return_code}")

        info("Installing ltchiptool with GUI extras...")
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

    @staticmethod
    def _install_python_windows(out_path: Path) -> Tuple[Path, Path]:
        version_spec = SimpleSpec("~3.11")

        info("Checking the latest Python version...")
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

        info(f"Will install Python {latest_version}")
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

        info(f"Downloading and extracting '{release_url}' to '{out_path}'...")
        with requests.get(release_url) as r:
            with ZipFile(BytesIO(r.content)) as z:
                z.extractall(out_path)

        info("Checking installed executable...")
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

        info("Enabling site-packages...")
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

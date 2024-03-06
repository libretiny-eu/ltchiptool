#  Copyright (c) Kuba Szczodrzyński 2024-3-6.

import platform
import shutil
from io import BytesIO
from os.path import expandvars
from pathlib import Path
from subprocess import PIPE, Popen
from typing import Tuple
from winreg import (
    HKEY_LOCAL_MACHINE,
    KEY_ALL_ACCESS,
    REG_SZ,
    CreateKeyEx,
    OpenKey,
    QueryValueEx,
    SetValue,
    SetValueEx,
)
from zipfile import ZipFile

import pylnk3
import requests
from semantic_version import SimpleSpec, Version
from win32comext.shell.shell import SHChangeNotify, SHGetFolderPath
from win32comext.shell.shellcon import (
    CSIDL_COMMON_DESKTOPDIRECTORY,
    CSIDL_DESKTOP,
    SHCNE_ASSOCCHANGED,
    SHCNF_IDLIST,
)
from win32con import HWND_BROADCAST, SMTO_ABORTIFHUNG, WM_SETTINGCHANGE
from win32gui import SendMessageTimeout

from .ltim import PYTHON_RELEASE_FILE_FMT, PYTHON_RELEASES, LTIMBase

PYTHON_WIN = "python.exe"
PYTHONW_WIN = "pythonw.exe"
ICON_FILE = "ltchiptool.ico"


class LTIM(LTIMBase):
    def _install_python(self, out_path: Path) -> Tuple[Path, Path]:
        version_spec = SimpleSpec("~3.11")

        self.callback.on_message("Checking the latest Python version")
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

        self.callback.on_message(f"Will install Python {latest_version}")
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

        self.callback.on_message(f"Downloading '{release_url}'")
        with requests.get(release_url, stream=True) as r:
            try:
                self.callback.on_total(int(r.headers["Content-Length"]))
            except ValueError:
                self.callback.on_total(-1)
            io = BytesIO()
            for chunk in r.iter_content(chunk_size=128 * 1024):
                self.callback.on_update(len(chunk))
                io.write(chunk)
        self.callback.on_total(None)

        self.callback.on_message(f"Extracting to '{out_path}'")
        with ZipFile(io) as z:
            self.callback.on_total(len(z.filelist))
            for member in z.filelist:
                z.extract(member, out_path)
        self.callback.on_total(None)

        self.callback.on_message("Checking installed executable")
        python_path = out_path / PYTHON_WIN
        pythonw_path = out_path / PYTHONW_WIN
        p = Popen(
            args=[python_path, "--version"],
            stdout=PIPE,
        )
        version_name, _ = p.communicate()
        if p.returncode != 0:
            raise RuntimeError(f"{python_path.name} returned {p.returncode}")
        version_tuple = version_name.decode().partition(" ")[2].split(".")

        self.callback.on_message("Enabling site-packages")
        pth_path = out_path / ("python%s%s._pth" % tuple(version_tuple[:2]))
        if not pth_path.is_file():
            raise RuntimeError(f"Extraction failed, {pth_path.name} is not a file")
        pth = pth_path.read_text()
        pth = pth.replace("#import site", "import site")
        pth_path.write_text(pth)

        self.callback.on_message("Installing icon resource")
        icon_path = out_path / ICON_FILE
        icon_res = self.get_gui_resource(ICON_FILE)
        shutil.copy(icon_res, icon_path)

        return python_path, pythonw_path

    def _install_shortcut(self, out_path: Path, public: bool) -> None:
        if public:
            desktop_dir = SHGetFolderPath(0, CSIDL_COMMON_DESKTOPDIRECTORY, 0, 0)
        else:
            desktop_dir = SHGetFolderPath(0, CSIDL_DESKTOP, 0, 0)

        gui_path = Path(desktop_dir) / "ltchiptool GUI.lnk"
        cli_path = Path(desktop_dir) / "ltchiptool CLI.lnk"

        self.callback.on_message("Creating desktop shortcuts")
        pylnk3.for_file(
            target_file=str(out_path / PYTHONW_WIN),
            lnk_name=str(gui_path),
            arguments="-m ltchiptool gui",
            description="Launch ltchiptool GUI",
            icon_file=str(out_path / ICON_FILE),
        )
        pylnk3.for_file(
            target_file=expandvars("%COMSPEC%"),
            lnk_name=str(cli_path),
            arguments="/K ltchiptool",
            description="Launch ltchiptool CLI",
            icon_file=str(out_path / ICON_FILE),
            work_dir=str(out_path / "Scripts"),
        )

    def _install_fta(self, out_path: Path, *fta: str) -> None:
        for ext in fta:
            ext = ext.lower().strip(".")
            self.callback.on_message(f"Associating {ext.upper()} file type")
            with OpenKey(HKEY_LOCAL_MACHINE, "SOFTWARE\\Classes") as classes:
                with CreateKeyEx(classes, f".{ext}") as ext_key:
                    SetValue(ext_key, "", REG_SZ, f"ltchiptool.{ext.upper()}")
                with CreateKeyEx(classes, f"ltchiptool.{ext.upper()}") as cls_key:
                    SetValue(cls_key, "", REG_SZ, f"ltchiptool {ext.upper()} file")
                    with CreateKeyEx(cls_key, "DefaultIcon") as icon_key:
                        SetValue(icon_key, "", REG_SZ, str(out_path / ICON_FILE))
                    with CreateKeyEx(cls_key, "shell") as shell_key:
                        SetValue(shell_key, "", REG_SZ, f"open")
                        with CreateKeyEx(shell_key, "open") as open_key:
                            with CreateKeyEx(open_key, "command") as command_key:
                                command = [
                                    str(out_path / PYTHONW_WIN),
                                    "-m",
                                    "ltchiptool",
                                    "gui",
                                    '"%1"',
                                ]
                                SetValue(command_key, "", REG_SZ, " ".join(command))
        self.callback.on_message("Notifying other programs")
        SHChangeNotify(SHCNE_ASSOCCHANGED, SHCNF_IDLIST, None, None)

    def _install_path(self, out_path: Path) -> None:
        script_path = out_path / "Scripts" / "ltchiptool.exe"
        bin_path = out_path / "bin" / "ltchiptool.exe"
        bin_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(script_path, bin_path)

        self.callback.on_message("Updating PATH variable")
        with OpenKey(
            HKEY_LOCAL_MACHINE,
            "SYSTEM\\CurrentControlSet\\Control\\Session Manager\\Environment",
            0,
            KEY_ALL_ACCESS,
        ) as key:
            new_dir = str(bin_path.parent)
            path, _ = QueryValueEx(key, "PATH")
            path = path.split(";")
            while new_dir in path:
                path.remove(new_dir)
            path.insert(0, new_dir)
            SetValueEx(key, "PATH", None, REG_SZ, ";".join(path))

        self.callback.on_message("Notifying other programs")
        SendMessageTimeout(
            HWND_BROADCAST,
            WM_SETTINGCHANGE,
            0,
            "Environment",
            SMTO_ABORTIFHUNG,
            5000,
        )

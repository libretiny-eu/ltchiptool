#  Copyright (c) Kuba Szczodrzyński 2023-12-14.

import shlex
import sys
from logging import info
from pathlib import Path

from ltchiptool.util.ltim import LTIM

from .base import BaseThread


class InstallThread(BaseThread):
    def __init__(
        self,
        out_path: Path,
        shortcut: str | None,
        fta: list[str],
        add_path: bool,
        relaunch: str = None,
    ):
        super().__init__()
        self.out_path = out_path
        self.shortcut = shortcut
        self.fta = fta
        self.add_path = add_path
        self.relaunch = relaunch

    def run_impl(self):
        if not self.relaunch:
            LTIM.get().install(
                out_path=self.out_path,
                shortcut=self.shortcut,
                fta=self.fta,
                add_path=self.add_path,
            )
            return

        from win32comext.shell.shell import ShellExecuteEx
        from win32comext.shell.shellcon import (
            SEE_MASK_NO_CONSOLE,
            SEE_MASK_NOCLOSEPROCESS,
        )
        from win32con import SW_SHOWNORMAL
        from win32event import INFINITE, WaitForSingleObject
        from win32process import GetExitCodeProcess

        prog = sys.executable.replace("python.exe", "pythonw.exe")
        args = []
        if not LTIM.get().is_bundled:
            args += list(sys.argv)
        args += ["install", str(self.out_path)]

        if self.shortcut:
            args += ["--shortcut", self.shortcut]
        for ext in self.fta:
            args += ["--fta", ext]
        if self.add_path:
            args += ["--add-path"]
        args = shlex.join(args).replace("'", '"')

        info(f"Launching: {prog} {args}")

        proc_info = ShellExecuteEx(
            nShow=SW_SHOWNORMAL,
            fMask=SEE_MASK_NOCLOSEPROCESS | SEE_MASK_NO_CONSOLE,
            lpVerb=self.relaunch == "uac" and "runas" or "",
            lpFile=prog,
            lpParameters=args,
        )
        handle = proc_info["hProcess"]
        WaitForSingleObject(handle, INFINITE)
        return_code = GetExitCodeProcess(handle)
        info(f"Process returned {return_code}")

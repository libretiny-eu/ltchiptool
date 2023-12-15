#  Copyright (c) Kuba Szczodrzyński 2023-12-15.

import os
from os.path import expandvars
from pathlib import Path

import wx.xrc

from ltchiptool.gui.utils import on_event
from ltchiptool.gui.work.install import InstallThread

from .base import BasePanel


class InstallPanel(BasePanel):
    def __init__(self, parent: wx.Window, frame):
        super().__init__(parent, frame)
        self.LoadXRC("InstallPanel")
        self.AddToNotebook("Install")

        self.BindButton("button_full", self.OnFullClick).SetAuthNeeded(True)
        self.BindButton("button_portable", self.OnPortableClick)
        self.BindButton("button_browse", self.OnBrowseClick)

        self.OutPath = self.BindTextCtrl("input_out_path")
        self.ShortcutNone = self.BindRadioButton("radio_shortcut_none")
        self.ShortcutPrivate = self.BindRadioButton("radio_shortcut_private")
        self.ShortcutPublic = self.BindRadioButton("radio_shortcut_public")

        self.FtaUf2 = self.BindCheckBox("checkbox_fta_uf2")
        self.FtaRbl = self.BindCheckBox("checkbox_fta_rbl")
        self.FtaBin = self.BindCheckBox("checkbox_fta_bin")

        self.AddPath = self.BindCheckBox("checkbox_add_path")

        self.Start = self.BindCommandButton("button_start", self.OnStartClick)
        self.Start.SetNote("")

        # noinspection PyTypeChecker
        self.OnFullClick(None)

    def OnUpdate(self, target: wx.Window = None):
        super().OnUpdate(target)

        auth_needed = [
            self.shortcut == "public",
            bool(self.fta),
            self.add_path,
        ]

        try:
            path = Path(self.out_path)
            if not path.is_absolute():
                path = None
            else:
                path = path.resolve()
                if path.is_file():
                    path = None
        except Exception:
            path = None

        if path and not any(auth_needed):
            test_path = path
            while not test_path.is_dir():
                test_path = test_path.parent
            test_file = test_path / "test_file.txt"
            can_write = os.access(test_path, os.W_OK)
            if can_write:
                try:
                    test_file.write_text("")
                    test_file.unlink(missing_ok=True)
                except (OSError, PermissionError, IOError):
                    can_write = False
            auth_needed.append(not can_write)

        self.Start.SetAuthNeeded(any(auth_needed))
        self.Start.Enable(bool(path))
        self.Start.SetNote("" if path else "Invalid target directory")

    @on_event
    def OnFullClick(self) -> None:
        path = expandvars("%PROGRAMFILES%\\kuba2k2\\ltchiptool")
        self.OutPath.SetValue(path)
        self.ShortcutPublic.SetValue(True)
        self.FtaUf2.SetValue(True)
        self.FtaRbl.SetValue(True)
        self.FtaBin.SetValue(False)
        self.AddPath.SetValue(False)
        self.DoUpdate(self.OutPath)

    @on_event
    def OnPortableClick(self) -> None:
        path = expandvars("%APPDATA%\\ltchiptool\\portable")
        self.OutPath.SetValue(path)
        self.ShortcutNone.SetValue(True)
        self.FtaUf2.SetValue(False)
        self.FtaRbl.SetValue(False)
        self.FtaBin.SetValue(False)
        self.AddPath.SetValue(False)
        self.DoUpdate(self.OutPath)

    @on_event
    def OnBrowseClick(self) -> None:
        with wx.DirDialog(
            parent=self,
            message="Choose directory",
            defaultPath=self.out_path,
            style=wx.DD_NEW_DIR_BUTTON,
        ) as dialog:
            dialog: wx.DirDialog
            if dialog.ShowModal() == wx.ID_CANCEL:
                return
            self.OutPath.SetValue(dialog.GetPath())

    @property
    def out_path(self) -> str:
        return self.OutPath.GetValue()

    @property
    def shortcut(self) -> str | None:
        if self.ShortcutPublic.GetValue():
            return "public"
        if self.ShortcutPrivate.GetValue():
            return "private"
        return None

    @property
    def fta(self) -> list[str]:
        result = []
        if self.FtaUf2.GetValue():
            result.append("uf2")
        if self.FtaRbl.GetValue():
            result.append("rbl")
        if self.FtaBin.GetValue():
            result.append("bin")
        return result

    @property
    def add_path(self) -> bool:
        return self.AddPath.GetValue()

    @on_event
    def OnStartClick(self) -> None:
        self.StartWork(
            InstallThread(
                relaunch="uac" if self.Start.GetAuthNeeded() else "normal",
                out_path=Path(self.out_path),
                shortcut=self.shortcut,
                fta=self.fta,
                add_path=self.add_path,
            )
        )

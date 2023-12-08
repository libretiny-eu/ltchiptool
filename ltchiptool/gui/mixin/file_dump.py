#  Copyright (c) Kuba Szczodrzyński 2023-11-28.

from datetime import datetime
from pathlib import Path

import wx

from ltchiptool.gui.base.panel import BasePanel
from ltchiptool.gui.utils import on_event, with_target
from ltchiptool.util.logging import verbose


# noinspection PyPep8Naming
class FileDumpBase(BasePanel):
    prev_file: Path | None = None
    auto_name: str | None = None
    File: wx.TextCtrl

    def __init__(self, parent: wx.Window, frame):
        super().__init__(parent, frame)

    def OnShow(self):
        super().OnShow()
        self.File.Bind(wx.EVT_KILL_FOCUS, self.OnBlur)
        self.EnableFileDrop()

    def GetFileSettings(self) -> dict:
        return dict(
            file=self.file and str(self.file),
            prev_file=self.prev_file and str(self.prev_file),
            auto_name=self.auto_name,
        )

    def SetFileSettings(
        self,
        file: str = None,
        prev_file: str = None,
        auto_name: str = None,
        **_,
    ):
        if file:
            self.file = Path(file)
        if prev_file:
            self.prev_file = Path(prev_file)
        if auto_name:
            self.auto_name = auto_name

    def OnFileDrop(self, *files) -> None:
        if not files:
            return
        self.prev_file = None
        self.set_writing()
        self.file = Path(files[0])

    @with_target
    def OnBlur(self, event: wx.FocusEvent, target: wx.Window) -> None:
        event.Skip()
        if target == self.File:
            self.file = self.file

    @on_event
    def OnBrowseClick(self) -> None:
        if self.is_writing:
            title = "Open file"
            flags = wx.FD_OPEN | wx.FD_FILE_MUST_EXIST
        else:
            title = "Save file"
            flags = wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT
        init_dir = self.file and self.file.parent or Path.cwd()
        init_file = (self.file and self.file.name) or (
            self.is_reading and self._make_dump_filename()
        )
        with wx.FileDialog(
            parent=self,
            message=title,
            defaultDir=str(init_dir),
            defaultFile=init_file or "",
            style=flags,
        ) as dialog:
            dialog: wx.FileDialog
            if dialog.ShowModal() == wx.ID_CANCEL:
                return
            self.file = Path(dialog.GetPath())

    def OnFileChanged(self, path: Path = None) -> bool | None:
        pass

    @property
    def filename_stem(self) -> str:
        return "dump"

    @property
    def filename_tags(self) -> str:
        return ""

    @property
    def is_reading(self) -> bool:
        raise NotImplementedError()

    @property
    def is_writing(self) -> bool:
        raise NotImplementedError()

    def set_writing(self) -> None:
        raise NotImplementedError()

    @property
    def file(self) -> Path | None:
        value = self.File.GetValue()
        return value and Path(value) or None

    @file.setter
    def file(self, value: Path | None) -> None:
        if self.OnFileChanged(value) is False:
            return
        self.File.ChangeValue(str(value or ""))
        self.DoUpdate(self.File)

    def generate_read_filename(self) -> None:
        if not self.prev_file:
            self.prev_file = self.file
        self._set_dump_filename()

    def regenerate_read_filename(self) -> None:
        if not self.file or self.file.name != self.auto_name:
            return
        self._set_dump_filename()

    def restore_write_filename(self) -> None:
        if self.prev_file:
            self.file = self.prev_file
            self.prev_file = None
        else:
            self.OnFileChanged(self.file)

    def _make_dump_filename(self) -> str:
        date = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        return f"ltchiptool_{self.filename_stem}_{date}{self.filename_tags}.bin"

    def _set_dump_filename(self) -> None:
        if not self.file:
            return
        self.auto_name = self._make_dump_filename()
        self.file = self.file.with_name(self.auto_name)
        verbose(f"Generated dump filename: {self.auto_name}")

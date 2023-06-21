#  Copyright (c) Kuba Szczodrzyński 2023-6-21.

import wx
import wx.xrc

from ltchiptool.gui.colors import ColorPalette

from .window import BaseWindow


# noinspection PyPep8Naming
class BaseFrame(wx.Frame, BaseWindow):
    Windows: dict[str, BaseWindow]

    def __init__(self, parent: wx.Window, frame):
        super().__init__(parent=parent)
        self.Main = frame
        self.Windows = {}
        self._threads = []
        self.Bind(wx.EVT_CLOSE, self.OnCloseButton)

    def SetInitParams(self, **kwargs):
        for window in self.Windows.values():
            window.SetInitParams(**kwargs)

    def GetSettings(self) -> dict:
        return {name: window.GetSettings() for name, window in self.Windows.items()}

    def SetSettings(self, **kwargs):
        for name, settings in kwargs.items():
            if name in self.Windows:
                self.Windows[name].SetSettings(**settings)

    def OnCloseButton(self, *_):
        self.Hide()

    def OnShow(self):
        for window in self.Windows.values():
            window.OnShow()

    def OnClose(self):
        super().OnClose()
        for window in self.Windows.values():
            window.OnClose()
        self.Destroy()

    def OnPaletteChanged(self, old: ColorPalette, new: ColorPalette):
        for window in self.Windows.values():
            window.OnClose()

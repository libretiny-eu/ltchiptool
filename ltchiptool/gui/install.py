#  Copyright (c) Kuba Szczodrzyński 2023-12-14.

from logging import INFO

import wx
import wx.xrc

from ltchiptool.util.logging import LoggingHandler
from ltchiptool.util.ltim import LTIM

from .base.window import BaseWindow
from .panels.log import LogPanel
from .utils import load_xrc_file
from .work.install import InstallThread


# noinspection PyPep8Naming
class InstallFrame(wx.Frame, BaseWindow):
    def __init__(self, install_kwargs: dict, *args, **kw):
        super().__init__(*args, **kw)

        xrc = LTIM.get().get_gui_resource("ltchiptool.xrc")
        icon = LTIM.get().get_gui_resource("ltchiptool.ico")
        self.Xrc = load_xrc_file(xrc)

        LoggingHandler.get().level = INFO
        LoggingHandler.get().exception_hook = self.ShowExceptionMessage

        self.Log = LogPanel(parent=self, frame=self)
        # noinspection PyTypeChecker
        self.Log.OnDonateClose(None)

        self.install_kwargs = install_kwargs

        self.Bind(wx.EVT_SHOW, self.OnShow)
        self.Bind(wx.EVT_CLOSE, self.OnClose)

        self.SetTitle("Installing ltchiptool")
        self.SetIcon(wx.Icon(str(icon), wx.BITMAP_TYPE_ICO))
        self.SetSize((1000, 400))
        self.SetMinSize((600, 200))
        self.Center()

    @staticmethod
    def ShowExceptionMessage(e, msg):
        wx.MessageBox(
            message="Installation failed!\n\nRefer to the log window for details.",
            caption="Error",
            style=wx.ICON_ERROR,
        )

    def OnShow(self, *_):
        self.InitWindow(self)
        self.StartWork(InstallThread(**self.install_kwargs))

    def OnClose(self, *_):
        self.StopWork(InstallThread)
        self.Destroy()

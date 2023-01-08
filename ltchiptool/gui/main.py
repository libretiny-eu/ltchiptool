#  Copyright (c) Kuba Szczodrzyński 2023-1-2.

import wx
import wx.adv
import wx.xrc

from ltchiptool.util import LoggingHandler

from .flash import FlashPanel
from .log import LogPanel


class MainFrame(wx.Frame):
    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)

        res = wx.xrc.XmlResource("d:\\Dev\\tuya\\wx\\wx.xrc")

        # initialize logging
        self.log = LogPanel(res, self)
        # main notebook
        self.notebook = wx.Notebook(self)
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.notebook, flag=wx.EXPAND)
        sizer.Add(self.log, proportion=1, flag=wx.EXPAND)
        self.SetSizer(sizer)

        try:
            # main menu
            menu_bar: wx.MenuBar = res.LoadMenuBar("MainMenuBar")
            self.SetMenuBar(menu_bar)

            self.flash = FlashPanel(res, self.notebook)

            self.notebook.AddPage(self.flash, "Flashing")
        except Exception as e:
            LoggingHandler.INSTANCE.emit_exception(e, True)

        self.Bind(wx.EVT_MENU, lambda event: self.Close(True), id=wx.ID_EXIT)

        self.SetSize((600, 800))
        self.SetMinSize((600, 600))
        self.CreateStatusBar()
        self.SetStatusText("Hello world")

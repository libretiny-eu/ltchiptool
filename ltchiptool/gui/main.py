#  Copyright (c) Kuba Szczodrzyński 2023-1-2.

import logging
import threading
from logging import debug, info

import wx
import wx.adv
import wx.xrc

from ltchiptool.util import LoggingHandler

from ._utils import with_target
from .flash import FlashPanel
from .log import LogPanel


class MainFrame(wx.Frame):
    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        threading.excepthook = lambda a: LoggingHandler.get().emit_exception(
            a.exc_value
        )

        res = wx.xrc.XmlResource("d:\\Dev\\tuya\\wx\\wx.xrc")

        # initialize logging
        self.Log = LogPanel(res, self)
        # main notebook
        self.Notebook = wx.Notebook(self)
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.Notebook, flag=wx.EXPAND)
        sizer.Add(self.Log, proportion=1, flag=wx.EXPAND)
        self.SetSizer(sizer)

        try:
            # main menu
            menu_bar: wx.MenuBar = res.LoadMenuBar("MainMenuBar")
            self.SetMenuBar(menu_bar)

            self.Flash = FlashPanel(res, self.Notebook)
            self.Notebook.AddPage(self.Flash, "Flashing")
        except Exception as e:
            LoggingHandler.get().emit_exception(e)

        self.Bind(wx.EVT_SHOW, self.OnShow)
        self.Bind(wx.EVT_CLOSE, self.OnClose)
        self.Bind(wx.EVT_MENU, self.OnMenu)

        self.SetSize((600, 800))
        self.SetMinSize((600, 600))
        self.CreateStatusBar()
        self.SetStatusText("Hello world")

    def OnShow(self, *_):
        debug("MainFrame OnShow()")
        self.Log.OnShow()
        self.Flash.OnShow()

    def OnClose(self, *_):
        debug("MainFrame OnClose()")
        self.Log.OnClose()
        self.Flash.OnClose()
        self.Destroy()

    @with_target
    def OnMenu(self, event: wx.CommandEvent, target: wx.Menu):
        item: wx.MenuItem = target.FindItemById(event.GetId())
        title = target.GetTitle()
        label = item.GetItemLabel()
        checked = item.IsChecked()

        match (title, label):
            case ("File", "Quit"):
                self.Close(True)

            case ("Logging", _) if label.startswith("Clear"):
                self.Log.Clear()

            case ("Logging", "Timed"):
                LoggingHandler.get().timed = checked
                info("Logging options changed")

            case ("Logging", "Colors"):
                LoggingHandler.get().raw = not checked
                info("Logging options changed")

            case ("Logging", ("Verbose" | "Debug" | "Info" | "Warning" | "Error") as l):
                level = logging.getLevelName(l.upper())
                LoggingHandler.get().level = level
                logging.log(level, "Log level changed")

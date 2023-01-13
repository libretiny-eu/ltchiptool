#  Copyright (c) Kuba Szczodrzyński 2023-1-2.

import json
import sys
import threading
from logging import debug, info
from os import makedirs
from os.path import dirname, isfile, join

import wx
import wx.adv
import wx.xrc
from click import get_app_dir

from ltchiptool.util import LoggingHandler

from ._base import BasePanel
from ._utils import with_target
from .flash import FlashPanel
from .log import LogPanel


# noinspection PyPep8Naming
class MainFrame(wx.Frame):
    panels: dict[str, BasePanel]

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        sys.excepthook = self.OnException
        threading.excepthook = self.OnException

        res = wx.xrc.XmlResource("d:\\Dev\\tuya\\wx\\wx.xrc")

        self.config_file = join(get_app_dir("ltchiptool"), "config.json")

        # initialize logging
        self.Log = LogPanel(res, self)
        # main window layout
        self.Notebook = wx.Notebook(self)
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.Notebook, flag=wx.EXPAND)
        sizer.Add(self.Log, proportion=1, flag=wx.EXPAND)
        self.SetSizer(sizer)

        try:
            self.SetMenuBar(res.LoadMenuBar("MainMenuBar"))

            self.Flash = FlashPanel(res, self.Notebook)
            self.Notebook.AddPage(self.Flash, "Flashing")
        except Exception as e:
            LoggingHandler.get().emit_exception(e)

        self.panels = dict(
            log=self.Log,
            flash=self.Flash,
        )

        self.Bind(wx.EVT_SHOW, self.OnShow)
        self.Bind(wx.EVT_CLOSE, self.OnClose)
        self.Bind(wx.EVT_MENU, self.OnMenu)

        self.SetSize((600, 800))
        self.SetMinSize((600, 600))
        self.CreateStatusBar()

    @property
    def _settings(self) -> dict:
        if not isfile(self.config_file):
            return dict()
        with open(self.config_file, "r") as f:
            return json.load(f)

    @_settings.setter
    def _settings(self, value: dict):
        makedirs(dirname(self.config_file), exist_ok=True)
        with open(self.config_file, "w") as f:
            json.dump(value, f, indent="\t")

    def GetSettings(self) -> dict:
        pass

    def SetSettings(self, **kwargs):
        pass

    @staticmethod
    def OnException(*args):
        if isinstance(args[0], type):
            LoggingHandler.get().emit_exception(args[1])
        else:
            LoggingHandler.get().emit_exception(args[0].exc_value)

    def OnShow(self, *_):
        settings = self._settings
        for name, panel in self.panels.items():
            panel.SetSettings(**settings.get(name, {}))
        if settings:
            info(f"Loaded settings from {self.config_file}")
        for name, panel in self.panels.items():
            panel.OnShow()

    def OnClose(self, *_):
        settings = dict()
        for name, panel in self.panels.items():
            panel.OnClose()
            settings[name] = panel.GetSettings() or {}
        self._settings = settings
        info(f"Saved settings to {self.config_file}")
        self.Destroy()

    @with_target
    def OnMenu(self, event: wx.CommandEvent, target: wx.Menu):
        if not isinstance(target, wx.Menu):
            # apparently EVT_MENU fires on certain key-presses too
            return
        item: wx.MenuItem = target.FindItemById(event.GetId())
        title = target.GetTitle()
        label = item.GetItemLabel()
        checked = item.IsChecked()

        match (title, label):
            case ("File", "Quit"):
                self.Close(True)
            case ("Debug", "Print settings"):
                for name, panel in self.panels.items():
                    debug(f"Panel '{name}' settings: {panel.GetSettings()}")
            case _:
                for panel in self.panels.values():
                    panel.OnMenu(title, label, checked)

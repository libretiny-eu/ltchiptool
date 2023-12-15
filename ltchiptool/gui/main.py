#  Copyright (c) Kuba Szczodrzyński 2023-1-2.

import os
from logging import debug, exception, info, warning
from os import rename, unlink
from os.path import isfile, join

import wx
import wx.xrc
import zeroconf
from click import get_app_dir

from ltchiptool.util.fileio import readjson, writejson
from ltchiptool.util.logging import LoggingHandler, verbose
from ltchiptool.util.lpm import LPM
from ltchiptool.util.ltim import LTIM
from ltchiptool.util.lvm import LVM

from .base.frame import BaseFrame
from .base.panel import BasePanel
from .base.window import BaseWindow
from .colors import ColorPalette
from .panels.log import LogPanel
from .utils import load_xrc_file, on_event, with_event, with_target


# noinspection PyPep8Naming
class MainFrame(wx.Frame):
    Windows: dict[str, BaseWindow]
    Panels: dict[str, BasePanel]
    Menus: dict[str, wx.Menu]
    MenuItems: dict[str, dict[str, wx.MenuItem]]
    NormalSize: wx.Size
    init_params: dict
    Zeroconf: zeroconf.Zeroconf | None = None

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        LoggingHandler.get().exception_hook = self.ShowExceptionMessage

        ltim = LTIM.get()
        xrc = ltim.get_gui_resource("ltchiptool.xrc")
        icon = ltim.get_gui_resource("ltchiptool.ico")
        self.Xrc = load_xrc_file(xrc)

        try:
            # try to find LT directory or local data snapshot
            LVM.get().require_version()
        except Exception as e:
            wx.MessageBox(message=str(e), caption="Error", style=wx.ICON_ERROR)
            wx.Exit()
            return

        old_config = join(get_app_dir("ltchiptool"), "config.json")
        self.config_file = join(get_app_dir("ltchiptool"), "gui.json")
        if isfile(old_config):
            # migrate old config to new filename
            if isfile(self.config_file):
                unlink(self.config_file)
            rename(old_config, self.config_file)
        self.loaded = False
        self.Windows = self.Panels = {}
        self.init_params = {}

        # main window layout
        self.Sizer = wx.BoxSizer(wx.VERTICAL)
        self.Splitter = wx.SplitterWindow(self, style=wx.SP_3D | wx.SP_LIVE_UPDATE)
        # build splitter panes
        self.Notebook = wx.Notebook(parent=self.Splitter)
        self.Notebook.SetMinSize((-1, 400))
        self.Log = LogPanel(parent=self.Splitter, frame=self)
        # initialize the splitter
        self.Splitter.SetMinimumPaneSize(150)
        self.Splitter.SetSashGravity(0.7)
        self.Splitter.SplitHorizontally(self.Notebook, self.Log, sashPosition=-300)
        self.Sizer.Add(self.Splitter, proportion=1, flag=wx.EXPAND)
        self.SetSizer(self.Sizer)
        self.Windows["log"] = self.Log

        # list all built-in panels
        from .panels.about import AboutPanel
        from .panels.flash import FlashPanel
        from .panels.install import InstallPanel
        from .panels.plugins import PluginsPanel

        windows = [
            ("flash", FlashPanel),
            ("plugins", (not ltim.is_bundled) and PluginsPanel),
            ("install", ltim.is_gui_entrypoint and os.name == "nt" and InstallPanel),
            ("about", AboutPanel),
        ]

        # load all panels from plugins
        lpm = LPM.get()
        for plugin in sorted(lpm.plugins, key=lambda p: p.title):
            if not plugin.is_compatible:
                continue
            if not plugin.has_gui:
                continue
            try:
                for gui_name, cls in plugin.build_gui().items():
                    windows.append((f"plugin.{plugin.namespace}.{gui_name}", cls))
            except Exception as e:
                exception(f"Couldn't build {plugin.namespace}", exc_info=e)

        # dummy name for exception messages
        name = "UI"
        try:
            self.SetMenuBar(self.Xrc.LoadMenuBar("MainMenuBar"))

            for name, cls in windows:
                if not cls:
                    continue
                if name.startswith("plugin."):
                    # mark as loaded after trying to build any plugin
                    self.loaded = True
                try:
                    if issubclass(cls, BasePanel):
                        panel = cls(parent=self.Notebook, frame=self)
                        self.Windows[name] = panel
                    elif issubclass(cls, BaseFrame):
                        frame = cls(parent=self, frame=self)
                        self.Windows[name] = frame
                    else:
                        warning(f"Unknown GUI element: {cls}")
                except Exception as e:
                    exception(f"Couldn't build {name}", exc_info=e)

            self.loaded = True
        except Exception as e:
            exception(f"Couldn't build {name}", exc_info=e)
            if not self.loaded:
                self.OnClose()

        # start zeroconf listener
        try:
            self.Zeroconf = zeroconf.Zeroconf()
        except Exception as e:
            warning("Couldn't start Zeroconf listener", exc_info=e)

        self.UpdateMenus()
        for title in sorted(ColorPalette.get_titles(), key=lambda t: t.lower()):
            self.Menus["Colors"].AppendRadioItem(wx.ID_ANY, title)
        self.UpdateMenus()

        self.Bind(wx.EVT_SHOW, self.OnShow)
        self.Bind(wx.EVT_CLOSE, self.OnClose)
        self.Bind(wx.EVT_MENU, self.OnMenu)
        self.Bind(wx.EVT_SIZE, self.OnSize)
        self.Notebook.Bind(wx.EVT_NOTEBOOK_PAGE_CHANGING, self.OnPageChanging)
        self.Notebook.Bind(wx.EVT_NOTEBOOK_PAGE_CHANGED, self.OnPageChanged)

        self.SetSize((750, 850))
        self.SetMinSize((700, 800))
        self.SetIcon(wx.Icon(str(icon), wx.BITMAP_TYPE_ICO))
        self.CreateStatusBar()

    @property
    def _settings(self) -> dict:
        return readjson(self.config_file) or {}

    @_settings.setter
    def _settings(self, value: dict):
        writejson(self.config_file, value)

    # noinspection PyPropertyAccess
    def GetSettings(self) -> dict:
        pos: wx.Point = self.GetPosition()
        size: wx.Size = self.NormalSize or self.GetSize()
        maximized: bool = self.IsMaximized()
        split: int = self.Splitter.GetSashPosition()
        page: str = self.NotebookPageName
        palette: str = self.palette
        return dict(
            pos=[pos.x, pos.y],
            size=[size.x, size.y],
            maximized=maximized,
            split=split,
            page=page,
            palette=palette,
        )

    def SetSettings(
        self,
        pos: tuple[int, int] = None,
        size: tuple[int, int] = None,
        maximized: bool = None,
        split: int = None,
        page: str = None,
        palette: str = None,
        **_,
    ):
        if pos:
            self.SetPosition(pos)
        if size:
            self.SetSize(size)
        if maximized:
            self.Maximize()
        if split:
            self.Splitter.SetSashPosition(split)
        if page is not None:
            self.NotebookPageName = page
        if palette is not None:
            self.palette = palette

    @property
    def NotebookPagePanel(self) -> BasePanel:
        return self.Notebook.GetCurrentPage()

    @NotebookPagePanel.setter
    def NotebookPagePanel(self, panel: BasePanel):
        prev_panel = self.NotebookPagePanel
        for i in range(self.Notebook.GetPageCount()):
            if panel == self.Notebook.GetPage(i):
                self.Notebook.SetSelection(i)
                if panel != prev_panel:
                    panel.OnActivate()
                    prev_panel.OnDeactivate()
                return

    @property
    def NotebookPageName(self) -> str:
        for name, panel in self.Windows.items():
            if panel == self.Notebook.GetCurrentPage():
                return name

    @NotebookPageName.setter
    def NotebookPageName(self, name: str):
        panel = self.Windows.get(name, None)
        if isinstance(panel, BasePanel):
            self.NotebookPagePanel = panel

    def UpdateMenus(self) -> None:
        self.MenuBar: wx.MenuBar = self.GetMenuBar()
        self.Menus = {}
        self.MenuItems = {}
        for menu, label in self.MenuBar.GetMenus():
            menu: wx.Menu
            self.Menus[label] = menu
            self.MenuItems[label] = {}
            for item in menu.GetMenuItems():
                item: wx.MenuItem
                self.MenuItems[label][item.GetItemLabel()] = item

    @staticmethod
    def ShowExceptionMessage(e, msg):
        lines = [msg] if msg else []
        while e:
            if type(e) in [RuntimeError, ValueError, OSError]:
                lines.append(str(e))
            else:
                lines.append(f"{type(e).__name__}: {e}")
            e = e.__context__
        lines.insert(1, "")
        wx.MessageBox(
            message="\n".join(lines),
            caption="Error",
            style=wx.ICON_ERROR,
        )

    def OnShow(self, *_):
        self.NotebookPagePanel.OnActivate()
        settings = self._settings
        self.SetSettings(**settings.get("main", {}))
        for name, window in self.Windows.items():
            window.SetSettings(**settings.get(name, {}))
            window.SetInitParams(**self.init_params)
        if settings:
            info(f"Loaded settings from {self.config_file}")
        for name, window in self.Windows.items():
            window.OnShow()

    def OnClose(self, *_):
        if not self.loaded:
            # avoid writing partial settings in case of loading failure
            self.Destroy()
            return
        settings = self._settings
        settings["main"] = self.GetSettings()
        for name, window in self.Windows.items():
            window.OnClose()
            window_settings = window.GetSettings() or {}
            if window_settings:
                settings[name] = window_settings
        self._settings = settings
        info(f"Saved settings to {self.config_file}")
        self.Destroy()

    @with_event
    def OnSize(self, event: wx.SizeEvent):
        event.Skip()
        if self.IsMaximized():
            return
        self.NormalSize = event.GetSize()

    @with_target
    def OnMenu(self, event: wx.CommandEvent, target: wx.Menu):
        if not isinstance(target, wx.Menu):
            # apparently EVT_MENU fires on certain key-presses too
            return
        item: wx.MenuItem = target.FindItemById(event.GetId())
        if not item:
            return
        title = target.GetTitle()
        label = item.GetItemLabel()
        checked = item.IsChecked() if item.IsCheckable() else False

        match (title, label):
            case ("File", "Quit"):
                self.Close(True)

            case ("Colors", _):
                self.palette = label

            case ("Debug", "Print settings"):
                debug(f"Main settings: {self.GetSettings()}")
                for name, window in self.Windows.items():
                    debug(f"Window '{name}' settings: {window.GetSettings()}")

            case _:
                for panel in self.Windows.values():
                    if isinstance(panel, BasePanel):
                        panel.OnMenu(title, label, checked)

    @with_event
    def OnPageChanging(self, event: wx.BookCtrlEvent):
        panel = self.NotebookPagePanel
        if not panel:
            return
        verbose(f"Deactivating page: {type(panel)}")
        if panel.OnDeactivate() is False:
            event.Veto()

    @on_event
    def OnPageChanged(self):
        panel = self.NotebookPagePanel
        if not panel:
            return
        verbose(f"Activating page: {type(panel)}")
        panel.OnActivate()

    @property
    def palette(self) -> str:
        return ColorPalette.get().name

    @palette.setter
    def palette(self, value: str) -> None:
        old = ColorPalette.get()
        new = ColorPalette.set(ColorPalette(value))
        item = self.MenuItems["Colors"][new.title]
        item.Check(True)
        for window in self.Windows.values():
            window.OnPaletteChanged(old, new)

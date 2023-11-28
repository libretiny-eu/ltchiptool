#  Copyright (c) Kuba Szczodrzyński 2023-1-3.

import threading
from logging import warning
from queue import Queue
from typing import Any, Callable, Tuple

import wx
import wx.adv
import wx.xrc

from ltchiptool.gui.utils import on_event

from .window import BaseWindow


# noinspection PyPep8Naming
class BasePanel(wx.Panel, BaseWindow):
    _components: list[wx.Window]
    _events: Queue[wx.Window | None]

    def __init__(self, parent: wx.Window, frame):
        super().__init__(parent)
        self.InitWindow(frame)
        self.Frame = frame
        self.Xrc: wx.xrc.XmlResource = frame.Xrc
        self._components = []
        self._events = Queue()
        self.Bind(wx.EVT_IDLE, self.OnIdle)

    def OnShow(self):
        self.OnUpdate()

    def OnActivate(self):
        pass

    def OnDeactivate(self):
        pass

    def _OnUpdate(self, event: wx.Event | None):
        if self._in_update:
            event.Skip()
            return
        self._in_update = True
        event.Skip()
        self.OnUpdate(event.GetEventObject() if event else None)
        self._in_update = False

    def DoUpdate(self, target: wx.Window = None):
        if self._in_update:
            return
        if threading.current_thread() != threading.main_thread():
            self._events.put(target)
            return
        self._in_update = True
        self.OnUpdate(target)
        self._in_update = False

    @on_event
    def OnIdle(self):
        while not self._events.empty():
            self.OnUpdate(self._events.get())

    def OnUpdate(self, target: wx.Window = None):
        pass

    def OnMenu(self, title: str, label: str, checked: bool):
        pass

    def OnFileDrop(self, *files):
        pass

    def LoadXRC(self, name: str, wrap_scrolled: bool = True):
        parent = self
        if wrap_scrolled:
            parent = wx.ScrolledWindow(self)
            parent.SetScrollRate(10, 10)
        panel = self.Xrc.LoadPanel(parent, name)
        if not panel:
            raise ValueError(f"Panel not found: {name}")
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(panel, 1, wx.EXPAND)
        if wrap_scrolled:
            parent.SetSizerAndFit(sizer)
            sizer = wx.BoxSizer(wx.VERTICAL)
            sizer.Add(parent, 1, wx.EXPAND)
        self.SetSizer(sizer)

    def AddToNotebook(self, title: str):
        self.Frame.Notebook.AddPage(self, title)

    def FindWindowByName(self, name, parent=None):
        if parent is None:
            warning(f"Passing parent=None to FindWindowByName in {self}")
            parent = self
        return super().FindWindowByName(name, parent)

    def BindByName(self, event: int, name: str, handler: Callable[[wx.Event], None]):
        self.FindWindowByName(name, self).Bind(event, handler)

    def BindComboBox(self, name: str):
        window: wx.ComboBox = self.FindWindowByName(name, self)
        self._components.append(window)
        # EVT_COMBOBOX fires EVT_TEXT as well
        window.Bind(wx.EVT_TEXT, self._OnUpdate)
        return window

    def BindListBox(self, name: str):
        window: wx.ListBox = self.FindWindowByName(name, self)
        self._components.append(window)
        window.Bind(wx.EVT_LISTBOX, self._OnUpdate)
        return window

    def BindRadioButton(self, name: str):
        window: wx.RadioButton = self.FindWindowByName(name, self)
        self._components.append(window)
        window.Bind(wx.EVT_RADIOBUTTON, self._OnUpdate)
        return window

    def BindCheckBox(self, name: str):
        window: wx.CheckBox = self.FindWindowByName(name, self)
        self._components.append(window)
        window.Bind(wx.EVT_CHECKBOX, self._OnUpdate)
        return window

    def BindTextCtrl(self, name: str):
        window: wx.TextCtrl = self.FindWindowByName(name, self)
        self._components.append(window)
        window.Bind(wx.EVT_TEXT, self._OnUpdate)
        return window

    def BindButton(self, name: str, func: Callable[[wx.Event], None]):
        window: wx.Button = self.FindWindowByName(name, self)
        self._components.append(window)
        window.Bind(wx.EVT_BUTTON, func)
        return window

    def BindCommandButton(self, name: str, func: Callable[[wx.Event], None]):
        window: wx.adv.CommandLinkButton = self.FindWindowByName(name, self)
        self._components.append(window)
        window.Bind(wx.EVT_BUTTON, func)
        return window

    def BindHyperlinkCtrl(self, name: str, func: Callable[[wx.Event], None] = None):
        window: wx.adv.HyperlinkCtrl = self.FindWindowByName(name, self)
        self._components.append(window)
        if func:
            window.Bind(wx.adv.EVT_HYPERLINK, func)
        return window

    def BindWindow(self, name: str, *handlers: Tuple[Any, Callable[[wx.Event], None]]):
        window = self.FindWindowByName(name, self)
        self._components.append(window)
        for event, func in handlers:
            window.Bind(event, func)
        return window

    def FindStaticText(self, name: str):
        window: wx.StaticText = self.FindWindowByName(name, self)
        return window

    def FindStaticBitmap(self, name: str):
        window: wx.StaticBitmap = self.FindWindowByName(name, self)
        return window

    def EnableAll(self):
        if self.is_closing:
            return
        for window in self._components:
            window.Enable()
        self.DoUpdate()

    def DisableAll(self):
        if self.is_closing:
            return
        for window in self._components:
            window.Disable()

    def EnableFileDrop(self):
        panel = self

        class FileDropTarget(wx.FileDropTarget):
            def __init__(self):
                wx.FileDropTarget.__init__(self)

            def OnDropFiles(self, x, y, filenames) -> bool:
                panel.OnFileDrop(*filenames)
                return True

        self.SetDropTarget(FileDropTarget())

    def DisableFileDrop(self):
        self.SetDropTarget(None)

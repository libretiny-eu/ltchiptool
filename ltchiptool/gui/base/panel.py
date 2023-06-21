#  Copyright (c) Kuba Szczodrzyński 2023-1-3.

from typing import Any, Callable, Tuple

import wx
import wx.xrc

from .window import BaseWindow


# noinspection PyPep8Naming
class BasePanel(wx.Panel, BaseWindow):
    _components: list[wx.Window]

    def __init__(self, parent: wx.Window, frame):
        super().__init__(parent)
        self.Frame = frame
        self.Xrc: wx.xrc.XmlResource = frame.Xrc
        self._components = []
        self._threads = []

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
        self._in_update = True
        self.OnUpdate(target)
        self._in_update = False

    def OnUpdate(self, target: wx.Window = None):
        pass

    def OnMenu(self, title: str, label: str, checked: bool):
        pass

    def OnFileDrop(self, *files):
        pass

    def LoadXRC(self, name: str):
        panel = self.Xrc.LoadPanel(self, name)
        if not panel:
            raise ValueError(f"Panel not found: {name}")
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(panel, 1, wx.EXPAND)
        self.SetSizer(sizer)

    def AddToNotebook(self, title: str):
        self.Frame.Notebook.AddPage(self, title)

    def BindByName(self, event: int, name: str, handler: Callable[[wx.Event], None]):
        self.FindWindowByName(name, self).Bind(event, handler)

    def BindComboBox(self, name: str):
        window: wx.ComboBox = self.FindWindowByName(name, self)
        self._components.append(window)
        window.Bind(wx.EVT_COMBOBOX, self._OnUpdate)
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
        self.OnUpdate()

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

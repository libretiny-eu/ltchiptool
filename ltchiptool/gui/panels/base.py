#  Copyright (c) Kuba Szczodrzyński 2023-1-3.

from typing import Callable

import wx
import wx.xrc

from ltchiptool.gui.work.base import BaseThread


# noinspection PyPep8Naming
class BasePanel(wx.Panel):
    _components: list[wx.Window]
    _threads: list[BaseThread]
    _in_update: bool = False
    is_closing: bool = False

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self._components = []
        self._threads = []

    def start_work(self, thread: BaseThread, freeze_ui: bool = False):
        self._threads.append(thread)

        def on_stop(t: BaseThread):
            self.on_work_stopped(t)
            if freeze_ui:
                self.EnableAll()

        thread.on_stop = on_stop
        if freeze_ui:
            self.DisableAll()
        thread.start()

    def stop_work(self, cls: type[BaseThread]):
        for t in list(self._threads):
            if isinstance(t, cls):
                t.stop()

    def on_work_stopped(self, t: BaseThread):
        self._threads.remove(t)

    def GetSettings(self) -> dict:
        pass

    def SetSettings(self, **kwargs):
        pass

    def OnShow(self):
        self.OnUpdate()

    def OnClose(self):
        self.is_closing = True
        for t in list(self._threads):
            t.stop()
            t.join()

    def OnMenu(self, title: str, label: str, checked: bool):
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

    def LoadXRC(self, res: wx.xrc.XmlResource, name: str):
        panel = res.LoadPanel(self, name)
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(panel, 1, wx.EXPAND)
        self.SetSizer(sizer)

    def BindByName(self, event: int, name: str, handler: Callable[[wx.Event], None]):
        self.FindWindowByName(name).Bind(event, handler)

    def BindComboBox(self, name: str):
        window: wx.ComboBox = self.FindWindowByName(name)
        self._components.append(window)
        window.Bind(wx.EVT_COMBOBOX, self._OnUpdate)
        return window

    def BindRadioButton(self, name: str):
        window: wx.RadioButton = self.FindWindowByName(name)
        self._components.append(window)
        window.Bind(wx.EVT_RADIOBUTTON, self._OnUpdate)
        return window

    def BindCheckBox(self, name: str):
        window: wx.CheckBox = self.FindWindowByName(name)
        self._components.append(window)
        window.Bind(wx.EVT_CHECKBOX, self._OnUpdate)
        return window

    def BindTextCtrl(self, name: str):
        window: wx.TextCtrl = self.FindWindowByName(name)
        self._components.append(window)
        window.Bind(wx.EVT_TEXT, self._OnUpdate)
        return window

    def BindButton(self, name: str, func: Callable[[wx.Event], None]):
        window: wx.Button = self.FindWindowByName(name)
        self._components.append(window)
        window.Bind(wx.EVT_BUTTON, func)
        return window

    def FindStaticText(self, name: str):
        window: wx.StaticText = self.FindWindowByName(name)
        return window

    def FindStaticBitmap(self, name: str):
        window: wx.StaticBitmap = self.FindWindowByName(name)
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

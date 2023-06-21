#  Copyright (c) Kuba Szczodrzyński 2023-6-21.

import sys
from os.path import dirname, isfile, join

import wx.xrc

from ltchiptool.gui.colors import ColorPalette
from ltchiptool.gui.utils import load_xrc_file
from ltchiptool.gui.work.base import BaseThread


# noinspection PyPep8Naming
class BaseWindow:
    Xrc: wx.xrc.XmlResource = None
    is_closing: bool = False
    _in_update: bool = False
    _threads: list[BaseThread]

    def StartWork(self, thread: BaseThread, freeze_ui: bool = True):
        self._threads.append(thread)

        def on_stop(t: BaseThread):
            self.OnWorkStopped(t)
            if freeze_ui:
                self.EnableAll()

        thread.on_stop = on_stop
        if freeze_ui:
            self.DisableAll()
        thread.start()

    def StopWork(self, cls: type[BaseThread]):
        for t in list(self._threads):
            if isinstance(t, cls):
                t.stop()

    def OnWorkStopped(self, t: BaseThread):
        self._threads.remove(t)

    def SetInitParams(self, **kwargs):
        pass

    def GetSettings(self) -> dict:
        pass

    def SetSettings(self, **kwargs):
        pass

    def OnShow(self):
        pass

    def OnClose(self):
        self.is_closing = True
        for t in list(self._threads):
            t.stop()
            t.join()

    def OnPaletteChanged(self, old: ColorPalette, new: ColorPalette):
        pass

    def LoadXRCFile(self, *path: str):
        xrc = join(*path)
        if isfile(xrc):
            self.Xrc = load_xrc_file(xrc)
        else:
            root = dirname(sys.modules[self.__module__].__file__)
            self.Xrc = load_xrc_file(root, *path)

    def EnableAll(self):
        pass

    def DisableAll(self):
        pass

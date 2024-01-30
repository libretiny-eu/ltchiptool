#  Copyright (c) Kuba Szczodrzyński 2023-6-21.

import sys
from os.path import dirname, isfile, join

import wx
import wx.lib.agw.genericmessagedialog as GMD
import wx.xrc

from ltchiptool.gui.colors import ColorPalette
from ltchiptool.gui.utils import load_xrc_file
from ltchiptool.gui.work.base import BaseThread

THREAD_STOP_ID = wx.NewIdRef()


class ThreadStopEvent(wx.PyCommandEvent):
    def __init__(self, thread: BaseThread, freeze_ui: bool):
        super().__init__(THREAD_STOP_ID)
        self.thread = thread
        self.freeze_ui = freeze_ui


# noinspection PyPep8Naming
class BaseWindow:
    Main: wx.Frame
    Xrc: wx.xrc.XmlResource = None
    is_closing: bool = False
    _in_update: bool = False
    _threads: list[BaseThread]

    def InitWindow(self, main) -> None:
        self.Main = main
        self._threads = []
        self.Connect(-1, -1, THREAD_STOP_ID, self._handle_thread_stop)

    def StartWork(self, thread: BaseThread, freeze_ui: bool = True):
        self._threads.append(thread)

        def on_stop(t: BaseThread):
            wx.PostEvent(self, ThreadStopEvent(t, freeze_ui))

        thread.on_stop = on_stop
        if freeze_ui:
            self.DisableAll()
        thread.start()

    def _handle_thread_stop(self, event: ThreadStopEvent):
        self._threads.remove(event.thread)
        if event.freeze_ui:
            self.EnableAll()
        self.OnWorkStopped(event.thread)

    def StopWork(self, cls: type[BaseThread]):
        for t in list(self._threads):
            if isinstance(t, cls):
                t.stop()

    def IsWorkRunning(self, cls: type[BaseThread]) -> bool:
        for t in list(self._threads):
            if isinstance(t, cls):
                return True
        return False

    def IsAnyWorkRunning(self) -> bool:
        return bool(self._threads)

    def OnWorkStopped(self, t: BaseThread):
        pass

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

    def MessageDialogMonospace(self, message: str, caption: str):
        dialog = GMD.GenericMessageDialog(
            parent=self,
            message=message,
            caption=caption,
            agwStyle=wx.ICON_INFORMATION | wx.OK,
        )
        # noinspection PyUnresolvedReferences
        font = wx.Font(wx.FontInfo(10).Family(wx.MODERN))
        dialog.SetFont(font)
        dialog.ShowModal()
        dialog.Destroy()

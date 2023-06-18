#  Copyright (c) Kuba Szczodrzyński 2023-1-8.

import logging
import threading
import time
from logging import INFO, info, log, warning

import wx
import wx.xrc
from click import _termui_impl
from click._termui_impl import ProgressBar
from serial import Serial

from ltchiptool.gui.colors import ColorPalette
from ltchiptool.util.logging import LoggingHandler
from ltchiptool.util.misc import sizeof
from ltchiptool.util.streams import LoggingStreamHook

from .base import BasePanel


class GUIProgressBar(ProgressBar):
    parent: BasePanel
    elapsed: wx.StaticText
    progress: wx.StaticText
    left: wx.StaticText
    time_elapsed: wx.StaticText
    time_left: wx.StaticText
    bar: wx.Gauge
    log: wx.TextCtrl
    scrolled: bool = False

    def format_time(self) -> str:
        t = int(time.time() - self.start)
        seconds = t % 60
        t //= 60
        minutes = t % 60
        t //= 60
        hours = t % 24
        t //= 24
        if t > 0:
            return f"{t}d {hours:02}:{minutes:02}:{seconds:02}"
        return f"{hours:02}:{minutes:02}:{seconds:02}"

    def render_progress(self) -> None:
        if self.parent.is_closing:
            return
        self.elapsed.Show()
        self.progress.Show()
        self.left.Show()
        self.time_elapsed.Show()
        self.time_left.Show()
        self.bar.Show()

        pct = self.format_pct()
        pos = sizeof(self.pos)
        length = sizeof(self.length)

        if self.length == 0:
            self.progress.SetLabel(self.label or "")
            self.bar.Pulse()
        else:
            if self.label:
                self.progress.SetLabel(f"{self.label} - {pct} ({pos} / {length})")
            else:
                self.progress.SetLabel(f"{pct} ({pos} / {length})")
            self.bar.SetRange(self.length)
            self.bar.SetValue(self.pos)

        self.time_elapsed.SetLabel(self.format_time())
        self.time_left.SetLabel(self.format_eta() or "--:--:--")

        self.parent.Layout()
        if not self.scrolled:
            self.log.AppendText("")
            self.scrolled = True

    def render_finish(self) -> None:
        if self.parent.is_closing:
            return
        self.elapsed.Hide()
        self.progress.Hide()
        self.left.Hide()
        self.time_elapsed.Hide()
        self.time_left.Hide()
        self.bar.Hide()
        self.parent.Layout()


class LogPanel(BasePanel):
    delayed_lines: list[tuple[str, str, str]] | None

    def __init__(self, parent: wx.Window, frame):
        super().__init__(parent, frame)
        self.LoadXRC("LogPanel")

        self.delayed_lines = []

        self.Log: wx.TextCtrl = self.FindWindowByName("text_log", self)
        LoggingHandler.get().add_emitter(self.emit_raw)

        GUIProgressBar.parent = self
        GUIProgressBar.elapsed = self.FindWindowByName("text_elapsed", self)
        GUIProgressBar.progress = self.FindWindowByName("text_progress", self)
        GUIProgressBar.left = self.FindWindowByName("text_left", self)
        GUIProgressBar.time_elapsed = self.FindWindowByName("text_time_elapsed", self)
        GUIProgressBar.time_left = self.FindWindowByName("text_time_left", self)
        GUIProgressBar.bar = self.FindWindowByName("progress_bar", self)
        GUIProgressBar.log = self.Log
        # noinspection PyTypeChecker
        GUIProgressBar.render_finish(GUIProgressBar)
        setattr(_termui_impl, "ProgressBar", GUIProgressBar)

    def emit_raw(self, log_prefix: str, message: str, color: str):
        # delay non-main-thread logging until the app finishes initializing
        is_main_thread = threading.current_thread() is threading.main_thread()
        if not is_main_thread and self.delayed_lines is not None:
            self.delayed_lines.append((log_prefix, message, color))
            return
        if self.is_closing:
            return

        wx_color = ColorPalette.get()[color]
        if LoggingHandler.get().raw:
            self.Log.SetDefaultStyle(wx.TextAttr(wx.WHITE))
        else:
            self.Log.SetDefaultStyle(wx.TextAttr(wx_color))
        self.Log.AppendText(f"{message}\n")

    def GetSettings(self) -> dict:
        handler = LoggingHandler.get()
        return dict(
            level=handler.level,
            timed=handler.timed,
            raw=handler.raw,
            full_traceback=handler.full_traceback,
            dump_serial=LoggingStreamHook.is_registered(Serial),
        )

    def SetSettings(
        self,
        level: int = INFO,
        timed: bool = False,
        raw: bool = False,
        full_traceback: bool = True,
        dump_serial: bool = False,
        **_,
    ):
        handler = LoggingHandler.get()
        handler.level = level
        handler.timed = timed
        handler.raw = raw
        handler.full_traceback = full_traceback
        LoggingStreamHook.set_registered(Serial, registered=dump_serial)

        menu_bar: wx.MenuBar = self.TopLevelParent.MenuBar
        menu: wx.Menu = menu_bar.GetMenu(menu_bar.FindMenu("Logging"))
        if not menu:
            warning(f"Couldn't find Logging menu")
            return
        level_name = logging.getLevelName(level).title()
        for item in menu.GetMenuItems():
            item: wx.MenuItem
            match item.GetItemLabel():
                case "Timed":
                    item.Check(timed)
                case "Colors":
                    item.Check(not raw)
                case "Dump serial data":
                    item.Check(dump_serial)
                case _ if item.GetItemLabel() == level_name:
                    item.Check()

    def OnShow(self):
        super().OnShow()
        if self.delayed_lines is None:
            return
        for log_prefix, message, color in self.delayed_lines:
            self.emit_raw(log_prefix, message, color)
        self.delayed_lines = None

    def OnClose(self):
        super().OnClose()
        LoggingHandler.get().clear_emitters()

    def OnMenu(self, title: str, label: str, checked: bool):
        if title != "Logging":
            return
        match label:
            case "Clear log window":
                self.Log.Clear()
            case "Timed":
                LoggingHandler.get().timed = checked
                info("Logging options changed")
            case "Colors":
                LoggingHandler.get().raw = not checked
                info("Logging options changed")
            case "Dump serial data":
                LoggingStreamHook.set_registered(Serial, registered=checked)
            case ("Verbose" | "Debug" | "Info" | "Warning" | "Error") as l:
                level = logging.getLevelName(l.upper())
                LoggingHandler.get().level = level
                log(level, "Log level changed")

    def OnPaletteChanged(self, old: ColorPalette, new: ColorPalette):
        new.apply(self.Log, old)

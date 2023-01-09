#  Copyright (c) Kuba Szczodrzyński 2023-1-8.

import threading
import time
from logging import debug, error, info, warning

import wx
import wx.xrc
from click import _termui_impl
from click._termui_impl import ProgressBar

from ltchiptool.util import LoggingHandler, sizeof, verbose

from ._base import BasePanel


class GUIProgressBar(ProgressBar):
    parent: wx.Window
    elapsed: wx.StaticText
    progress: wx.StaticText
    left: wx.StaticText
    time_elapsed: wx.StaticText
    time_left: wx.StaticText
    bar: wx.Gauge

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
        self.elapsed.Show()
        self.progress.Show()
        self.left.Show()
        self.time_elapsed.Show()
        self.time_left.Show()
        self.bar.Show()

        pct = self.format_pct()
        pos = sizeof(self.pos)
        length = sizeof(self.length)
        self.progress.Label = f"{pct} ({pos} / {length})"
        self.time_elapsed.Label = self.format_time()
        self.time_left.Label = self.format_eta() or "--:--:--"
        self.bar.SetRange(self.length)
        self.bar.SetValue(self.pos)
        self.parent.Layout()

    def render_finish(self) -> None:
        self.elapsed.Hide()
        self.progress.Hide()
        self.left.Hide()
        self.time_elapsed.Hide()
        self.time_left.Hide()
        self.bar.Hide()
        self.parent.Layout()


class LogPanel(BasePanel):
    COLOR_MAP = {
        "black": wx.Colour(12, 12, 12),
        "red": wx.Colour(197, 15, 31),
        "green": wx.Colour(19, 161, 14),
        "yellow": wx.Colour(193, 156, 0),
        "blue": wx.Colour(0, 55, 218),
        "magenta": wx.Colour(136, 23, 152),
        "cyan": wx.Colour(58, 150, 221),
        "white": wx.Colour(204, 204, 204),
        "bright_black": wx.Colour(118, 118, 118),
        "bright_red": wx.Colour(231, 72, 86),
        "bright_green": wx.Colour(22, 198, 12),
        "bright_yellow": wx.Colour(249, 241, 165),
        "bright_blue": wx.Colour(59, 120, 255),
        "bright_magenta": wx.Colour(180, 0, 158),
        "bright_cyan": wx.Colour(97, 214, 214),
        "bright_white": wx.Colour(242, 242, 242),
    }

    delayed_lines: list[tuple[str, str, str]] | None

    def __init__(self, res: wx.xrc.XmlResource, *args, **kw):
        super().__init__(*args, **kw)
        self.LoadXRC(res, "LogPanel")

        self.delayed_lines = []

        self.Log: wx.TextCtrl = self.FindWindowByName("text_log")
        LoggingHandler.get().add_emitter(self.emit_raw)
        verbose("Hello World")
        debug("Hello World")
        info("Hello World")
        warning("Hello World")
        error("Hello World")

        GUIProgressBar.parent = self
        GUIProgressBar.elapsed = self.FindWindowByName("text_elapsed")
        GUIProgressBar.progress = self.FindWindowByName("text_progress")
        GUIProgressBar.left = self.FindWindowByName("text_left")
        GUIProgressBar.time_elapsed = self.FindWindowByName("text_time_elapsed")
        GUIProgressBar.time_left = self.FindWindowByName("text_time_left")
        GUIProgressBar.bar = self.FindWindowByName("progress_bar")
        # noinspection PyTypeChecker
        GUIProgressBar.render_finish(GUIProgressBar)
        setattr(_termui_impl, "ProgressBar", GUIProgressBar)

    def emit_raw(self, log_prefix: str, message: str, color: str):
        # delay non-main-thread logging until the app finishes initializing
        is_main_thread = threading.current_thread() is threading.main_thread()
        if not is_main_thread and self.delayed_lines is not None:
            self.delayed_lines.append((log_prefix, message, color))
            return

        wx_color = self.COLOR_MAP[color]
        if LoggingHandler.get().raw:
            self.Log.SetDefaultStyle(wx.TextAttr(wx.WHITE))
        else:
            self.Log.SetDefaultStyle(wx.TextAttr(wx_color))
        self.Log.AppendText(f"{message}\n")

    def Clear(self):
        self.Log.Clear()

    def OnShow(self):
        super().OnShow()
        for log_prefix, message, color in self.delayed_lines:
            self.emit_raw(log_prefix, message, color)
        self.delayed_lines = None

    def OnClose(self):
        super().OnClose()
        LoggingHandler.get().clear_emitters()

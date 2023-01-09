#  Copyright (c) Kuba Szczodrzyński 2023-1-8.
import threading
import time
from logging import debug, error, info, warning

import wx
import wx.xrc
from click import _termui_impl
from click._termui_impl import ProgressBar

from ltchiptool.util import VERBOSE, LoggingHandler, log_setup, sizeof, verbose

from ._base import BasePanel


class GUILoggingHandler(LoggingHandler):
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

    def __init__(self, log: wx.TextCtrl) -> None:
        super().__init__()
        self.log = log
        self.delayed_lines = []

    def emit_raw(self, log_prefix: str, message: str, color: str):
        # delay non-main-thread logging until the app finishes initializing
        is_main_thread = threading.current_thread() is threading.main_thread()
        if not is_main_thread and self.delayed_lines is not None:
            self.delayed_lines.append((log_prefix, message, color))
            return

        wx_color = self.COLOR_MAP[color]
        if self.raw:
            self.log.SetDefaultStyle(wx.TextAttr(wx.WHITE))
        else:
            self.log.SetDefaultStyle(wx.TextAttr(wx_color))
        self.log.AppendText(f"{message}\n")
        super().emit_raw(log_prefix, message, color)

    def print_delayed(self):
        for log_prefix, message, color in self.delayed_lines:
            self.emit_raw(log_prefix, message, color)
        self.delayed_lines = None


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
    def __init__(self, res: wx.xrc.XmlResource, *args, **kw):
        super().__init__(*args, **kw)

        self.LoadXRC(res, "LogPanel")

        self.log: wx.TextCtrl = self.FindWindowByName("text_log")
        self.handler = GUILoggingHandler(self.log)
        self.set_level(VERBOSE)
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

    def set_level(self, level: int) -> None:
        log_setup(level=level, handler=self.handler, setup_bars=False)

    def set_options(self, timed: bool, raw: bool) -> None:
        self.handler.timed = timed
        self.handler.raw = raw

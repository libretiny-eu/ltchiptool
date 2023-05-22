#  Copyright (c) Kuba Szczodrzyński 2023-1-3.

from os.path import join
from typing import Callable

import wx
import wx.xrc


def with_target(
    func: Callable[[object, wx.Event, wx.Window], None],
) -> Callable[[wx.Event], None]:
    return lambda self, event: func(self, event, event.EventObject if event else None)


def only_target(
    func: Callable[[object, wx.Window], None],
) -> Callable[[wx.Event], None]:
    return lambda self, event: func(self, event.EventObject if event else None)


def on_event(
    func: Callable[[object], None],
) -> Callable[[wx.Event], None]:
    return lambda self, event: func(self)


def with_event(
    func: Callable[[object, wx.Event], None],
) -> Callable[[wx.Event], None]:
    return lambda self, event: func(self, event)


def int_or_zero(value: str) -> int:
    try:
        return int(value, 0)
    except ValueError:
        if value.startswith("0"):
            return int_or_zero(value.lstrip("0"))
        return 0


def load_xrc_file(*path: str) -> wx.xrc.XmlResource:
    xrc = join(*path)
    try:
        with open(xrc, "r") as f:
            xrc_str = f.read()
            xrc_str = xrc_str.replace("<object>", '<object class="notebookpage">')
        res = wx.xrc.XmlResource()
        res.LoadFromBuffer(xrc_str.encode())
        return res
    except SystemError:
        raise FileNotFoundError(f"Couldn't load the layout file '{xrc}'")

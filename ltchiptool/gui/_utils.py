#  Copyright (c) Kuba Szczodrzyński 2023-1-3.

from typing import Callable

import wx


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

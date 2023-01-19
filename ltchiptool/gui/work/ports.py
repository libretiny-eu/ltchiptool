#  Copyright (c) Kuba Szczodrzyński 2023-1-9.

from time import sleep
from typing import Callable

from ltchiptool.util.cli import list_serial_ports
from ltchiptool.util.logging import verbose

from .base import BaseThread


# Win32 part based on https://abdus.dev/posts/python-monitor-usb/
class PortWatcher(BaseThread):
    def __init__(self, on_event: Callable[[list[tuple[str, bool, str]]], None]):
        super().__init__()
        self.on_event = on_event

    def _create_window(self):
        """
        Create a window for listening to messages
        https://docs.microsoft.com/en-us/windows/win32/learnwin32/creating-a-window#creating-the-window

        See also: https://docs.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-createwindoww

        :return: window hwnd
        """
        import win32api
        import win32gui

        wc = win32gui.WNDCLASS()
        wc.lpfnWndProc = self._on_message
        wc.lpszClassName = self.__class__.__name__
        wc.hInstance = win32api.GetModuleHandle(None)
        class_atom = win32gui.RegisterClass(wc)
        return win32gui.CreateWindow(
            class_atom, self.__class__.__name__, 0, 0, 0, 0, 0, 0, 0, wc.hInstance, None
        )

    def _on_message(self, hwnd: int, msg: int, wparam: int, lparam: int):
        from win32con import (
            DBT_DEVICEARRIVAL,
            DBT_DEVICEREMOVECOMPLETE,
            WM_DEVICECHANGE,
        )

        if msg != WM_DEVICECHANGE:
            return 0
        if wparam not in [DBT_DEVICEARRIVAL, DBT_DEVICEREMOVECOMPLETE]:
            return 0
        self.on_event(list_serial_ports())
        return 0

    def run_impl_win32(self):
        """
        Listens to Win32 `WM_DEVICECHANGE` messages
        and trigger a callback when a device has been plugged in or out

        See: https://docs.microsoft.com/en-us/windows/win32/devio/wm-devicechange
        """
        import win32gui

        hwnd = self._create_window()
        verbose(f"Created listener window with hwnd={hwnd:x}")
        self.on_event(list_serial_ports())
        verbose("Listening to messages")
        while self.should_run():
            win32gui.PumpWaitingMessages()
            sleep(0.5)
        verbose("Listener stopped")

    def run_impl(self):
        import platform

        match platform.system():
            case "Windows":
                self.run_impl_win32()
            case _:
                verbose("Running dummy PortWatcher impl")
                self.on_event(list_serial_ports())

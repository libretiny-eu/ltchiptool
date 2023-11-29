#  Copyright (c) Kuba Szczodrzyński 2023-1-9.

from logging import debug, error
from multiprocessing import Lock
from queue import Empty, Queue
from typing import Callable

from ltchiptool.util.logging import verbose

from .base import BaseThread


# Win32 part based on https://abdus.dev/posts/python-monitor-usb/
class DeviceWatcher(BaseThread):
    handlers: list[Callable[[], None]] = None
    call_queue: Queue[Callable[[], None]] = None
    in_message: bool = False
    lock: Lock = None

    def __init__(self):
        super().__init__()
        self.handlers = []
        self.call_queue = Queue()
        self.lock = Lock()

    def _create_window(self):
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
            DBT_DEVNODES_CHANGED,
            WM_DEVICECHANGE,
        )

        if self.in_message:
            return 0
        if msg != WM_DEVICECHANGE:
            return 0
        if wparam not in [
            DBT_DEVICEARRIVAL,
            DBT_DEVICEREMOVECOMPLETE,
            DBT_DEVNODES_CHANGED,
        ]:
            return 0
        self.in_message = True
        debug(f"Window message: {msg:X}, wparam={wparam:X}")
        self._call_all()
        self.in_message = False
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
        verbose("Listening to messages")
        while self.should_run():
            win32gui.PumpWaitingMessages()
            self._call_queued()
        verbose("Listener stopped")

    def _call_all(self) -> None:
        for handler in self.handlers:
            try:
                with self.lock:
                    handler()
            except Exception as e:
                error("DeviceWatcher handler threw an exception", exc_info=e)

    def _call_queued(self) -> None:
        try:
            func = self.call_queue.get(block=True, timeout=0.3)
            with self.lock:
                func()
        except Empty:
            pass
        except Exception as e:
            error("DeviceWatcher handler threw an exception", exc_info=e)

    def schedule_call(self, func: Callable[[], None]) -> None:
        self.call_queue.put(func)

    def run_impl(self):
        import platform

        self._call_all()

        match platform.system():
            case "Windows":
                self.run_impl_win32()
            case _:
                verbose("Running dummy PortWatcher impl")
                while True:
                    self._call_queued()

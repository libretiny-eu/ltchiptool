#  Copyright (c) Kuba Szczodrzyński 2023-1-9.

from logging import debug, error
from queue import Empty, Queue
from threading import Lock
from typing import Callable

from ltchiptool.util.logging import verbose

from .base import BaseThread


# Win32 part based on https://abdus.dev/posts/python-monitor-usb/
class DeviceWatcher(BaseThread):
    handlers: list[Callable[[], None]] = None
    call_queue: Queue[Callable[[], None]] = None
    in_message: bool = False
    lock: Lock = None
    _class_atom: int | None = None
    _windows: dict[int, "DeviceWatcher"] = {}

    def __init__(self):
        super().__init__()
        self.handlers = []
        self.call_queue = Queue()
        self.lock = Lock()

    @classmethod
    def _wnd_proc(cls, hwnd: int, msg: int, wparam: int, lparam: int):
        # the window class is shared by all watchers in the process,
        # so dispatch to the watcher owning this window
        watcher = cls._windows.get(hwnd)
        if watcher is None:
            return 0
        return watcher._on_message(hwnd, msg, wparam, lparam)

    def _create_window(self):
        import win32api
        import win32gui

        hinstance = win32api.GetModuleHandle(None)
        if DeviceWatcher._class_atom is None:
            # Win32 window classes live as long as the process, so register only once
            wc = win32gui.WNDCLASS()
            wc.lpfnWndProc = DeviceWatcher._wnd_proc
            wc.lpszClassName = DeviceWatcher.__name__
            wc.hInstance = hinstance
            DeviceWatcher._class_atom = win32gui.RegisterClass(wc)
        hwnd = win32gui.CreateWindow(
            DeviceWatcher._class_atom,
            DeviceWatcher.__name__,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            hinstance,
            None,
        )
        DeviceWatcher._windows[hwnd] = self
        return hwnd

    def _destroy_window(self, hwnd: int) -> None:
        import win32gui

        DeviceWatcher._windows.pop(hwnd, None)
        try:
            win32gui.DestroyWindow(hwnd)
        except Exception as e:
            verbose(f"Couldn't destroy listener window: {e}")

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
        try:
            while self.should_run():
                win32gui.PumpWaitingMessages()
                self._call_queued()
        finally:
            self._destroy_window(hwnd)
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
                while self.should_run():
                    self._call_queued()

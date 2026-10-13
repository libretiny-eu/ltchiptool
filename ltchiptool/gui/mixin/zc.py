#  Copyright (c) Kuba Szczodrzyński 2023-8-31.

from logging import debug, warning
from threading import RLock

import wx
from zeroconf import ServiceBrowser, ServiceInfo, ServiceListener, Zeroconf

from ltchiptool.gui.main import MainFrame


# noinspection PyPep8Naming
class ZeroconfBase(ServiceListener):
    Main: MainFrame
    _zeroconf_browsers: dict[str, ServiceBrowser] = None
    _zeroconf_services: dict[str, ServiceInfo] = None
    _zeroconf_lock: RLock = None

    def AddZeroconfBrowser(self, type_: str) -> None:
        if self._zeroconf_browsers is None:
            self._zeroconf_browsers = {}
            self._zeroconf_services = {}
            self._zeroconf_lock = RLock()
        if not self.Main or not self.Main.Zeroconf:
            return
        if type_ in self._zeroconf_browsers:
            return
        self._zeroconf_browsers[type_] = ServiceBrowser(self.Main.Zeroconf, type_, self)

    def StopZeroconf(self) -> None:
        if self._zeroconf_browsers is None:
            return
        # cancel outside the lock - it joins the browser thread, which may need the lock
        browsers = list(self._zeroconf_browsers.values())
        for sb in browsers:
            sb.cancel()
        with self._zeroconf_lock:
            self._zeroconf_browsers.clear()
            self._zeroconf_services.clear()
        self._NotifyZeroconf()

    def _NotifyZeroconf(self) -> None:
        # called from zeroconf threads - never touch the GUI from here;
        # pass a snapshot to the main thread instead
        with self._zeroconf_lock:
            services = dict(self._zeroconf_services)
        if wx.IsMainThread():
            self.OnZeroconfUpdate(services)
        else:
            wx.CallAfter(self._DeliverZeroconf, services)

    def _DeliverZeroconf(self, services: dict[str, ServiceInfo]) -> None:
        if getattr(self, "is_closing", False):
            return
        self.OnZeroconfUpdate(services)

    def OnZeroconfUpdate(self, services: dict[str, ServiceInfo]):
        pass

    def add_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        debug(f"Zeroconf service added: {name}")
        info = zc.get_service_info(type_, name)
        with self._zeroconf_lock:
            if info:
                self._zeroconf_services[name] = info
            else:
                warning("Couldn't read service info")
        self._NotifyZeroconf()

    def update_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        debug(f"Zeroconf service updated: {name}")
        info = zc.get_service_info(type_, name)
        with self._zeroconf_lock:
            if info:
                self._zeroconf_services[name] = info
            else:
                warning("Couldn't read service info")
                self._zeroconf_services.pop(name, None)
        self._NotifyZeroconf()

    def remove_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        debug(f"Zeroconf service removed: {name}")
        with self._zeroconf_lock:
            self._zeroconf_services.pop(name, None)
        self._NotifyZeroconf()

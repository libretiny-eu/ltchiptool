#  Copyright (c) Kuba Szczodrzyński 2023-8-31.

from logging import debug, warning

from zeroconf import ServiceBrowser, ServiceInfo, ServiceListener, Zeroconf

from ltchiptool.gui.main import MainFrame


# noinspection PyPep8Naming
class ZeroconfBase(ServiceListener):
    Main: MainFrame
    _zeroconf_browsers: dict[str, ServiceBrowser] = None
    _zeroconf_services: dict[str, ServiceInfo] = None

    def AddZeroconfBrowser(self, type_: str) -> None:
        if self._zeroconf_browsers is None:
            self._zeroconf_browsers = {}
            self._zeroconf_services = {}
        if not self.Main or not self.Main.Zeroconf:
            return
        if type_ in self._zeroconf_browsers:
            return
        self._zeroconf_browsers[type_] = ServiceBrowser(self.Main.Zeroconf, type_, self)

    def StopZeroconf(self) -> None:
        if self._zeroconf_browsers is None:
            return
        for sb in self._zeroconf_browsers.values():
            sb.cancel()
        self._zeroconf_browsers.clear()
        self._zeroconf_services.clear()
        self.OnZeroconfUpdate(self._zeroconf_services)

    def OnZeroconfUpdate(self, services: dict[str, ServiceInfo]):
        pass

    def add_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        debug(f"Zeroconf service added: {name}")
        info = zc.get_service_info(type_, name)
        if info:
            self._zeroconf_services[name] = info
        else:
            warning("Couldn't read service info")
        self.OnZeroconfUpdate(self._zeroconf_services)

    def update_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        debug(f"Zeroconf service updated: {name}")
        info = zc.get_service_info(type_, name)
        if info:
            self._zeroconf_services[name] = info
        else:
            warning("Couldn't read service info")
            self._zeroconf_services.pop(name, None)
        self.OnZeroconfUpdate(self._zeroconf_services)

    def remove_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        debug(f"Zeroconf service removed: {name}")
        self._zeroconf_services.pop(name, None)
        self.OnZeroconfUpdate(self._zeroconf_services)

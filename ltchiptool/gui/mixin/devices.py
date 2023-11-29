#  Copyright (c) Kuba Szczodrzyński 2023-11-28.

from ltchiptool.gui.base.window import BaseWindow
from ltchiptool.gui.main import MainFrame
from ltchiptool.gui.work.devices import DeviceWatcher
from ltchiptool.util.misc import list_serial_ports


# noinspection PyPep8Naming
class DevicesBase(BaseWindow):
    Main: MainFrame
    WATCHER: DeviceWatcher = None

    def StartDeviceWatcher(self) -> None:
        if not DevicesBase.WATCHER:
            watcher = DevicesBase.WATCHER = DeviceWatcher()
            watcher.on_stop = self.OnWatcherStopped
            watcher.start()
        else:
            watcher = DevicesBase.WATCHER
        watcher.handlers.append(self.OnDevicesUpdated)
        watcher.schedule_call(self.OnDevicesUpdated)

    def CallDeviceWatcher(self, *_, **__) -> None:
        if not DevicesBase.WATCHER:
            return
        DevicesBase.WATCHER.schedule_call(self.OnDevicesUpdated)

    def StopDeviceWatcher(self) -> None:
        if not DevicesBase.WATCHER:
            return
        watcher = DevicesBase.WATCHER
        if self.OnDevicesUpdated in watcher.handlers:
            watcher.handlers.remove(self.OnDevicesUpdated)

    def OnClose(self):
        super().OnClose()
        if watcher := DevicesBase.WATCHER:
            watcher.stop()
            watcher.join()

    @staticmethod
    def OnWatcherStopped(*_) -> None:
        DevicesBase.WATCHER = None

    def OnDevicesUpdated(self) -> None:
        self.OnPortsUpdated(list_serial_ports())

    def OnPortsUpdated(self, ports: list[tuple[str, bool, str]]) -> None:
        pass

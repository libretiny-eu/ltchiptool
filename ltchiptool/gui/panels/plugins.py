#  Copyright (c) Kuba Szczodrzyński 2023-5-21.

from dataclasses import dataclass
from enum import Enum

import wx.dataview
import wx.xrc
from wx._dataview import DataViewItemArray
from wx.dataview import DataViewCtrl, DataViewItem, NullDataViewItem, PyDataViewModel

from ltchiptool.gui.utils import on_event, with_event
from ltchiptool.gui.work.plugins import PluginsThread
from ltchiptool.util.lpm import LPM
from ltctplugin.base import PluginBase

from .base import BasePanel


class PluginType(Enum):
    INSTALLED = "Installed"
    DOWNLOAD = "Download"


@dataclass
class PluginModel:
    namespace: str = None
    plugin: PluginBase = None
    result: LPM.SearchResult = None

    @property
    def distribution(self) -> str:
        return (
            self.plugin
            and self.plugin.distribution.name
            or self.result
            and self.result.distribution
            or ""
        )

    @property
    def title(self) -> str:
        namespace = self.namespace
        plugin = self.plugin
        result = self.result
        return plugin and plugin.title or result and result.distribution or namespace

    @property
    def has_update(self) -> bool:
        plugin = self.plugin
        result = self.result
        return plugin and result and plugin.version != result.latest

    @property
    def is_disabled(self) -> bool:
        namespace = self.namespace
        plugin = self.plugin
        return namespace and not plugin or False

    def sort_key(self):
        return not self.has_update, self.is_disabled, self.title.lower()


# noinspection PyPep8Naming
class PluginsDataModel(PyDataViewModel):
    def __init__(self):
        super().__init__()
        self.items: list[PluginModel] = []
        self.Installed = self.ObjectToItem(PluginType.INSTALLED)
        self.Download = self.ObjectToItem(PluginType.DOWNLOAD)
        self.item_no_installed = self.ObjectToItem("No plugins installed")
        self.item_no_download = self.ObjectToItem("Press Download plugins...")

    def UpdateItems(
        self,
        disabled: set[str],
        plugins: list[PluginBase],
        results: list[LPM.SearchResult],
    ):
        added: list[PluginModel] = []
        changed: list[PluginModel] = []
        deleted: list[PluginModel] = list(self.items)

        def by_namespace(value: str):
            for model in self.items:
                if value == model.namespace:
                    return model
            return None

        def by_plugin(value: PluginBase):
            for model in self.items:
                if value == model.plugin or model.namespace == value.namespace:
                    return model
            return None

        def by_result(value: LPM.SearchResult):
            for model in self.items:
                if model.distribution == value.distribution:
                    return model
            return None

        def check_model(model: PluginModel | None) -> PluginModel:
            if model:
                if model not in changed:
                    changed.append(model)
                if model in deleted:
                    deleted.remove(model)
            else:
                model = PluginModel()
                added.append(model)
                self.items.append(model)
            return model

        # update disabled plugins
        for namespace in disabled:
            found = check_model(by_namespace(namespace))
            found.namespace = namespace
            found.plugin = None
            found.result = None
        # update enabled plugins
        for plugin in plugins:
            found = check_model(by_plugin(plugin))
            found.namespace = plugin.namespace
            found.plugin = plugin
            found.result = None
        # update search results
        for result in results:
            found = check_model(by_result(result))
            found.result = result

        self.items.sort(key=lambda m: m.sort_key())

        # apply model deletions
        for obj in deleted:
            item = self.ObjectToItem(obj)
            parent = self.Installed if obj.plugin or obj.namespace else self.Download
            self.ItemDeleted(parent, item)
            if obj in self.items:
                self.items.remove(obj)
        # apply model changes
        for obj in changed:
            item = self.ObjectToItem(obj)
            self.ItemChanged(item)
        # apply model insertions
        for obj in added:
            item = self.ObjectToItem(obj)
            parent = self.Installed if obj.plugin or obj.namespace else self.Download
            self.ItemAdded(parent, item)

        installed = [i for i in self.items if i.plugin or i.namespace]
        download = [i for i in self.items if not i.plugin and i.result]
        self.ItemDeleted(self.Installed, self.item_no_installed)
        self.ItemDeleted(self.Download, self.item_no_download)
        if not installed:
            self.ItemAdded(self.Installed, self.item_no_installed)
        if not download:
            self.ItemAdded(self.Download, self.item_no_download)

    def IsContainer(self, item: DataViewItem):
        if item == NullDataViewItem:
            return True
        obj = self.ItemToObject(item)
        return isinstance(obj, PluginType)

    def GetChildren(self, item: DataViewItem, children: DataViewItemArray):
        if item == NullDataViewItem:
            items = [PluginType.INSTALLED, PluginType.DOWNLOAD]
        else:
            obj: PluginType = self.ItemToObject(item)
            match obj:
                case PluginType.INSTALLED:
                    items = [i for i in self.items if i.plugin or i.namespace]
                    if not items:
                        children.append(self.item_no_installed)
                        return 1
                case PluginType.DOWNLOAD:
                    items = [i for i in self.items if not i.plugin and i.result]
                    if not items:
                        children.append(self.item_no_download)
                        return 1
                case _:
                    return 0
        for item in items:
            children.append(self.ObjectToItem(item))
        return len(items)

    def GetParent(self, item: DataViewItem):
        if item == NullDataViewItem:
            return NullDataViewItem
        obj: PluginModel | PluginType = self.ItemToObject(item)
        if not isinstance(obj, PluginModel):
            return NullDataViewItem
        if obj.plugin or obj.namespace:
            return self.Installed
        if not obj.plugin and obj.result:
            return self.Download
        return NullDataViewItem

    def GetValue(self, item: DataViewItem, col: int):
        obj = self.ItemToObject(item)
        cols = []
        match obj:
            case PluginType(value=text):
                return text
            case str(text) if col == 0:
                return text
            case PluginModel(_, plugin, result):
                cols = [
                    obj.title,
                    plugin and plugin.version,
                    result and result.latest,
                    result and result.description or plugin and plugin.description,
                ]
        try:
            return cols[col]
        except IndexError:
            return None


class PluginsPanel(BasePanel):
    def __init__(self, parent: wx.Window, frame):
        super().__init__(parent, frame)
        self.LoadXRC("PluginsPanel")
        self.AddToNotebook("Plugins")

        self.lpm = LPM.get()
        self.model = PluginsDataModel()
        self.results: list[LPM.SearchResult] = []

        self.Tree: DataViewCtrl = self.BindWindow(
            "plugins_tree",
            (wx.dataview.EVT_DATAVIEW_SELECTION_CHANGED, self.OnSelectionChanged),
            (wx.dataview.EVT_DATAVIEW_ITEM_ACTIVATED, self.OnItemActivated),
        )
        self.Tree.AssociateModel(self.model)
        self.Tree.AppendTextColumn("Title", 0, width=180)
        self.Tree.AppendTextColumn("Version", 1, width=60)
        self.Tree.AppendTextColumn("Latest", 2, width=60)
        self.Tree.AppendTextColumn("Description", 3, width=-1)

        self.BindButton("button_download", self.OnDownloadClick)
        self.InstallInput = self.BindTextCtrl("input_install")
        self.InstallButton = self.BindButton("button_install", self.OnInstallClick)

    def OnWorkStopped(self, t: PluginsThread):
        super().OnWorkStopped(t)
        if t.search:
            self.results = t.results
        self.model.UpdateItems(
            disabled=self.lpm.disabled,
            plugins=self.lpm.plugins,
            results=self.results,
        )
        self.Tree.Expand(self.model.Installed)
        self.Tree.Expand(self.model.Download)
        if t.install:
            if t.success:
                wx.MessageBox(
                    message=(
                        "Plugin installation succeeded.\n"
                        "Restart the app to apply changes."
                    ),
                    caption="Success",
                )
            else:
                wx.MessageBox(
                    message=(
                        "Plugin installation failed.\n"
                        "Consult the log window for more details."
                    ),
                    caption="Failure",
                    style=wx.ICON_ERROR,
                )

    def OnActivate(self):
        self.StartWork(PluginsThread(scan=True))

    def OnDeactivate(self):
        self.model.items = []
        self.model.Cleared()

    @with_event
    def OnSelectionChanged(self, event: wx.dataview.DataViewEvent):
        item = event.GetItem()
        if item == NullDataViewItem:
            return
        obj = self.model.ItemToObject(item)
        if not isinstance(obj, PluginModel):
            return
        distribution = obj.distribution
        self.InstallInput.SetValue(distribution)

    def OnUpdate(self, target: wx.Window = None):
        self.InstallButton.Enable(not not self.InstallInput.Value)

    @with_event
    def OnItemActivated(self, event: wx.dataview.DataViewEvent):
        item = event.GetItem()
        obj = self.model.ItemToObject(item)
        match obj:
            case PluginType():
                if self.Tree.IsExpanded(item):
                    self.Tree.Collapse(item)
                else:
                    self.Tree.Expand(item)
            case PluginModel(namespace, plugin, result):
                obj: PluginModel
                lines = [obj.title, ""]
                if obj.has_update:
                    lines += [
                        "An update is available!",
                        f"{obj.plugin.version} -> {obj.result.latest}",
                        "",
                    ]
                if plugin:
                    lines += [
                        f"Version: {plugin.version}",
                        plugin.description and f"Description: {plugin.description}",
                        plugin.author and f"Author: {plugin.author}",
                        plugin.license and f"License: {plugin.license}",
                        f"Type: {plugin.type_text}",
                        f"Distribution: {plugin.distribution.name}",
                        f"Namespace: {plugin.namespace}",
                        f"Module: {plugin.module}",
                    ]
                elif result:
                    lines += [
                        f"Distribution: {result.distribution}",
                        result.latest and f"Latest version: {result.latest}",
                        result.description and f"Description: {result.description}",
                    ]
                elif namespace:
                    f"Plugin is disabled"

                message = "\n".join(line for line in lines if line is not None)
                wx.MessageBox(message, caption=obj.title)

    @on_event
    def OnDownloadClick(self):
        self.StartWork(PluginsThread(search=True))

    @on_event
    def OnInstallClick(self):
        distribution = self.InstallInput.GetValue()
        if not distribution:
            wx.MessageBox(
                message="Enter plugin name first",
                caption="Missing name",
                style=wx.OK | wx.ICON_WARNING | wx.CENTRE,
            )
            return
        self.StartWork(PluginsThread(install=distribution))

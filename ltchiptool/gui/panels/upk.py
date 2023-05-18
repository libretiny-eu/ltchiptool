#  Copyright (c) Kuba Szczodrzyński 2023-5-13.

import json
import os
from logging import debug, error, info, warning
from os.path import dirname, isfile

import requests
import wx
import wx.adv
import wx.xrc

from ltchiptool.gui.utils import on_event
from ltchiptool.gui.work.upk import UpkThread
from ltchiptool.util.logging import LoggingHandler

from .base import BasePanel

DISCLAIMER_TEXT = """
While the author has taken care to write the converter as well as possible, keep in mind that this might not be 100% accurate!

There may be some errors, such as missing components (unsupported types) or incorrect readings.

This serves mostly as a kickstart config, rather than a production-ready file. Make sure to review the output before uploading it to the device.

**We do not take responsibility for using this tool and the generated configs.**
"""


class UpkPanel(BasePanel):
    last_dir: str = None
    last_url: str = None
    logs_shown: bool = False
    disclaimer_shown: bool = False

    def __init__(self, res: wx.xrc.XmlResource, *args, **kw):
        super().__init__(*args, **kw)
        self.LoadXRC(res, "UpkPanel")

        self.Notebook: wx.Notebook = self.FindWindowByName("notebook_upk")

        self.BindButton("button_kickstart", self.on_do_kickstart_click)
        self.BindButton("button_cloudcutter", self.on_do_cloudcutter_click)
        self.BindButton("button_dump", self.on_do_dump_click)

        self.Opts: dict[str, wx.CheckBox | wx.TextCtrl] = {
            "esphome_block": self.BindCheckBox("opts_esphome_block"),
            "name_mac": self.BindCheckBox("opts_name_mac"),
            "common": self.BindCheckBox("opts_common"),
            "web_server": self.BindCheckBox("opts_web_server"),
            "restart": self.BindCheckBox("opts_restart"),
            "uptime": self.BindCheckBox("opts_uptime"),
            "lt_version": self.BindCheckBox("opts_lt_version"),
            "wifi_ssid": self.BindTextCtrl("opts_wifi_ssid"),
            "wifi_password": self.BindTextCtrl("opts_wifi_password"),
            "ota_password": self.BindTextCtrl("opts_ota_password"),
            "api_password": self.BindTextCtrl("opts_api_password"),
        }
        self.BindButton("button_generate", self.on_generate_click)
        self.BindButton("button_esphome_copy", self.on_esphome_copy_click)

        self.TextEsphome = self.BindTextCtrl("input_esphome")
        self.TextUpk = self.BindTextCtrl("input_upk")
        self.TextStorage = self.BindTextCtrl("input_storage")

        self.EnableFileDrop()

    def GetSettings(self) -> dict:
        return dict(
            opts={key: value.GetValue() for key, value in self.Opts.items()},
            last_dir=self.last_dir,
            last_url=self.last_url,
            disclaimer_shown=self.disclaimer_shown,
        )

    def SetSettings(
        self,
        opts: dict = None,
        last_dir: str = None,
        last_url: str = None,
        disclaimer_shown: bool = None,
        **_,
    ):
        if opts:
            for key, value in opts.items():
                if key in self.Opts:
                    self.Opts[key].SetValue(value)
        if last_dir:
            self.last_dir = last_dir
        if last_url:
            self.last_url = last_url
        if disclaimer_shown is not None:
            self.disclaimer_shown = disclaimer_shown

    def OnUpdate(self, target: wx.Window = None):
        if target is None:
            return
        debug(f"OnUpdate, target: {type(target)}, upk: {self.upk}")
        upk = self.upk
        if not upk:
            self.TextEsphome.Clear()
            self.logs_shown = False
            return
        if target == self.TextUpk:
            self.logs_shown = False

        if not self.disclaimer_shown:
            wx.MessageBox(
                message=DISCLAIMER_TEXT,
                caption="Disclaimer",
                style=wx.ICON_WARNING,
            )
            self.disclaimer_shown = True

        try:
            import upk2esphome
        except (ImportError, ModuleNotFoundError):
            wx.MessageBox(
                message=(
                    "upk2esphome package is not installed. Install it using:\n\n"
                    "pip install upk2esphome"
                ),
                caption="Error",
                style=wx.ICON_ERROR,
            )
            return

        from upk2esphome import Opts, generate_yaml

        opts = Opts(**self.GetSettings()["opts"])
        yr = generate_yaml(upk, opts)
        self.TextEsphome.ChangeValue(yr.text)

        if not self.logs_shown:
            self.logs_shown = True
            for line in yr.errors:
                error(line)
            if yr.errors:
                wx.MessageBox(
                    message="While generating YAML:\n\n" + "\n".join(yr.errors),
                    caption="Error",
                    style=wx.ICON_ERROR,
                )
            for line in yr.warnings:
                warning(line)
            if yr.warnings:
                wx.MessageBox(
                    message="While generating YAML:\n\n" + "\n".join(yr.warnings),
                    caption="Warning",
                    style=wx.ICON_WARNING,
                )
            for line in yr.logs:
                info(f"UPK: {line}")

    def on_storage_data(self, storage: dict):
        self.storage = storage
        self.DoUpdate()

    def on_storage_error(self, error_text: str):
        self.storage = None
        self.DoUpdate()
        wx.MessageBox(
            message=error_text,
            caption="Error",
            style=wx.ICON_ERROR,
        )

    def OnFileDrop(self, *files):
        if not files:
            return
        file = files[0]
        if not isfile(file):
            return
        self.last_dir = dirname(file)
        work = UpkThread(
            file=file,
            on_storage=self.on_storage_data,
            on_error=self.on_storage_error,
        )
        self.start_work(work, freeze_ui=True)

    @on_event
    def on_do_kickstart_click(self):
        dialog = wx.TextEntryDialog(
            self,
            message="Enter URL (or IP address) of Kickstart dashboard:",
            caption="Kickstart URL",
            value=self.last_url or "",
        )
        if dialog.ShowModal() != wx.ID_OK:
            dialog.Destroy()
            return
        url = dialog.GetValue().strip()
        dialog.Destroy()
        if not url:
            return

        debug(f"Kickstart URL: {url}")
        self.last_url = url
        work = UpkThread(
            url=url,
            on_storage=self.on_storage_data,
            on_error=self.on_storage_error,
        )
        self.start_work(work, freeze_ui=True)

    @on_event
    def on_do_cloudcutter_click(self):
        self.DisableAll()
        try:
            url = "https://tuya-cloudcutter.github.io/api/devices.json"
            with requests.get(url) as r:
                if r.status_code != 200:
                    self.EnableAll()
                    wx.MessageBox(
                        message=(
                            "Couldn't download Cloudcutter device list.\n"
                            f"Status code: {r.status_code}"
                        ),
                        caption="Error",
                        style=wx.ICON_ERROR,
                    )
                    return
                devices = r.json()
        except Exception as e:
            self.EnableAll()
            LoggingHandler.get().emit_exception(e)
            return
        self.EnableAll()

        for device in devices:
            device["name"] = f'{device["manufacturer"]} - {device["name"]}'
        devices = sorted(devices, key=lambda d: d["name"])

        devices_slug = [device["slug"] for device in devices]
        devices_name = [device["name"] for device in devices]

        dialog = wx.SingleChoiceDialog(
            self,
            message="Choose a Cloudcutter profile, that matches your particular device:",
            caption="Cloudcutter profile",
            choices=devices_name,
        )
        if dialog.ShowModal() != wx.ID_OK:
            dialog.Destroy()
            return
        selection = dialog.GetSelection()
        dialog.Destroy()

        slug = devices_slug[selection]
        debug(f"Selection: {slug}")

        self.DisableAll()
        try:
            url = f"https://tuya-cloudcutter.github.io/api/devices/{slug}.json"
            with requests.get(url) as r:
                if r.status_code != 200:
                    self.EnableAll()
                    wx.MessageBox(
                        message=(
                            f"Couldn't download Cloudcutter device '{slug}'.\n"
                            f"Status code: {r.status_code}"
                        ),
                        caption="Error",
                        style=wx.ICON_ERROR,
                    )
                    return
                device = r.json()
        except Exception as e:
            self.EnableAll()
            LoggingHandler.get().emit_exception(e)
            return
        self.EnableAll()

        self.storage = None
        self.upk = device.get("device_configuration", {})

    @on_event
    def on_do_dump_click(self):
        title = "Open file"
        flags = wx.FD_OPEN | wx.FD_FILE_MUST_EXIST
        init_dir = self.last_dir or os.getcwd()
        with wx.FileDialog(self, title, init_dir, style=flags) as dialog:
            dialog: wx.FileDialog
            if dialog.ShowModal() == wx.ID_CANCEL:
                return
            file = dialog.GetPath()
            self.last_dir = dirname(file)
            work = UpkThread(
                file=file,
                on_storage=self.on_storage_data,
                on_error=self.on_storage_error,
            )
            self.start_work(work, freeze_ui=True)

    @on_event
    def on_generate_click(self):
        self.Notebook.SetSelection(2)

    @on_event
    def on_esphome_copy_click(self):
        text = self.TextEsphome.GetValue()
        clip = wx.TextDataObject()
        clip.SetText(text)
        if wx.TheClipboard.Open():
            wx.TheClipboard.SetData(clip)
            wx.TheClipboard.Flush()
            self.TextEsphome.SelectAll()

    @property
    def upk(self):
        text = self.TextUpk.GetValue() or None
        return text and json.loads(text)

    @upk.setter
    def upk(self, value: dict | None):
        text = value and json.dumps(value, indent=4) or ""
        self.TextUpk.ChangeValue(text)
        if value:
            # valid UPK, go to options page
            self.Notebook.SetSelection(1)
        elif value is not None:
            # empty UPK == no UPK in storage
            wx.MessageBox(
                message=(
                    "This device doesn't contain user_param_key config. "
                    "Possible causes:\n"
                    "- it has custom/non-generic firmware\n"
                    "- it uses TuyaMCU\n\n"
                    "Auto-generating ESPHome YAML is not possible."
                ),
                caption="Missing configuration",
                style=wx.ICON_WARNING,
            )
        # else: UPK is None, so we're clearing the state
        self.DoUpdate(self.TextUpk)

    @property
    def storage(self):
        text = self.TextStorage.GetValue() or None
        return text and json.loads(text)

    @storage.setter
    def storage(self, value: dict | None):
        text = value and json.dumps(value, indent=4) or ""
        self.TextStorage.ChangeValue(text)
        if value is None:
            # clear UPK along with storage
            self.upk = None
        else:
            # set UPK if present, or set empty if not
            self.upk = value.get("user_param_key", {})
        self.DoUpdate(self.TextStorage)

#  Copyright (c) Kuba Szczodrzyński 2023-1-2.

import os
from enum import Enum, auto
from logging import info
from os.path import dirname, isfile
from threading import Thread
from time import sleep
from typing import List, Optional, Tuple

import click
import wx
import wx.adv
import wx.xrc

from ltchiptool import Family
from ltchiptool.commands.flash._utils import get_file_type
from ltchiptool.util import verbose
from uf2tool.models import UF2

from ._base import BasePanel
from ._utils import on_event, only_target
from .work.ports import PortWatcher


class FlashOp(Enum):
    WRITE = auto()
    READ = auto()
    READ_ROM = auto()


class FlashPanel(BasePanel):
    file_tuple: Optional[tuple] = None
    ports: List[Tuple[str, bool, str]]

    def __init__(self, res: wx.xrc.XmlResource, *args, **kw):
        super().__init__(*args, **kw)
        self.LoadXRC(res, "FlashPanel")

        self.ports = []

        self.Port = self.BindComboBox("combo_port")
        self.Write = self.BindRadioButton("radio_write")
        self.Read = self.BindRadioButton("radio_read")
        self.ReadROM = self.BindRadioButton("radio_read_rom")
        self.AutoDetect = self.BindCheckBox("checkbox_auto_detect")
        self.FileText = self.FindStaticText("text_file")
        self.File = self.BindTextCtrl("input_file")
        self.Family = self.BindComboBox("combo_family")
        self.BindButton("button_browse", self.on_browse_click)
        self.Start: wx.adv.CommandLinkButton = self.BindButton(
            "button_start", self.on_start_click
        )

        self.FileType: wx.TextCtrl = self.FindWindowByName("input_file_type")

        self.OffsetText: wx.StaticText = self.FindWindowByName("text_offset")
        self.Offset: wx.TextCtrl = self.FindWindowByName("input_offset")
        self.SkipText: wx.StaticText = self.FindWindowByName("text_skip")
        self.Skip: wx.TextCtrl = self.FindWindowByName("input_skip")
        self.LengthText: wx.StaticText = self.FindWindowByName("text_length")
        self.Length: wx.TextCtrl = self.FindWindowByName("input_length")

        self.Family.Set([f.description for f in Family.get_all() if f.name])

    def OnShow(self):
        super().OnShow()
        self.start_work(PortWatcher(self.on_ports_updated))

    def OnUpdate(self, target: wx.Window = None):
        if target in [self.File]:
            self.file = self.file

        self.Family.Enable(self.operation != FlashOp.WRITE or not self.auto_detect)
        self.Offset.Enable(not self.auto_detect)
        self.SkipText.Enable(self.operation == FlashOp.WRITE)
        self.Skip.Enable(self.operation == FlashOp.WRITE and not self.auto_detect)
        self.Length.Enable(not self.auto_detect)

        errors = []
        warnings = []

        if self.operation == FlashOp.WRITE:
            self.FileText.SetLabel("Input file")
            self.LengthText.SetLabel("Writing length")
            if not self.file:
                errors.append("Choose an input file")
            elif self.file_tuple is None:
                errors.append("File does not exist")
            else:
                file_type, family, _, offset, skip, length = self.file_tuple
                self.offset = offset
                self.skip = skip
                self.length = length
                self.FileType.SetValue(file_type or "Unrecognized")
                self.AutoDetect.Enable(file_type != "UF2")
                if self.auto_detect:
                    self.family = family

                if file_type == "UF2":
                    if not self.auto_detect:
                        self.auto_detect = True
                        self.OnUpdate()
                        return
                elif not file_type and self.auto_detect:
                    errors.append("File is unrecognized")
                elif not file_type:
                    warnings.append("Warning: file is unrecognized")
                    self.FileType.SetValue(file_type or "Raw")
                elif not family and self.auto_detect:
                    errors.append("File is not directly flashable")
                elif not offset and self.auto_detect:
                    errors.append(f"File is not flashable to '{family.description}'")
                elif not (family and offset):
                    warnings.append("Warning: file is not flashable")
                elif not self.auto_detect:
                    warnings.append("Warning: using custom options")
        else:
            self.FileText.SetLabel("Output file")
            self.LengthText.SetLabel("Reading length")
            if not self.file:
                errors.append("Choose an output file")
            self.skip = 0
            if self.auto_detect:
                self.offset = 0
                self.length = 0x200000

        verbose(f"Update: family={self.family}")

        if not self.family:
            errors.append("Choose the chip family")
        if not self.length:
            errors.append("Enter a correct length")

        if errors:
            self.Start.SetNote(errors[0])
            self.Start.Disable()
        elif warnings:
            self.Start.SetNote(warnings[0])
            self.Start.Enable()
        else:
            self.Start.SetNote("")
            self.Start.Enable()

    @property
    def port(self):
        if self.Port.GetSelection() == wx.NOT_FOUND:
            return None
        return self.ports[self.Port.GetSelection()][0]

    @port.setter
    def port(self, value: Optional[str]):
        if value is None:
            self.Port.SetSelection(wx.NOT_FOUND)
        else:
            for port, _, description in self.ports:
                if value == port:
                    self.Port.SetValue(description)

    @property
    def operation(self):
        if self.Write.GetValue():
            return FlashOp.WRITE
        if self.Read.GetValue():
            return FlashOp.READ
        if self.ReadROM.GetValue():
            return FlashOp.READ_ROM

    @property
    def auto_detect(self):
        return self.AutoDetect.IsChecked()

    @auto_detect.setter
    def auto_detect(self, value: bool):
        self.AutoDetect.SetValue(value)

    @property
    def family(self):
        try:
            return Family.get(description=self.Family.GetValue())
        except ValueError:
            return None

    @family.setter
    def family(self, value: Optional[Family]):
        self.Family.SetSelection(wx.NOT_FOUND)
        if value:
            self.Family.SetValue(value.description)

    @property
    def file(self):
        return self.File.GetValue()

    @file.setter
    def file(self, value: str):
        self.File.ChangeValue(value)
        if self.operation != FlashOp.WRITE:
            return
        if not isfile(value):
            self.file_tuple = None
        else:
            with open(value, "rb") as f:
                tpl = get_file_type(None, f)
                if tpl[0] == "UF2":
                    uf2 = UF2(f)
                    uf2.read(block_tags=False)
                    family = uf2.family
                    tpl = tuple([tpl[0], family, *tpl[2:]])
                self.file_tuple = tpl

    @property
    def offset(self):
        text: str = self.Offset.GetValue().strip() or "0"
        value = int(text, 0)
        self.Offset.SetValue(f"0x{value:X}")
        return value

    @offset.setter
    def offset(self, value: int):
        value = value or 0
        self.Offset.SetValue(f"0x{value:X}")

    @property
    def skip(self):
        text: str = self.Skip.GetValue().strip() or "0"
        value = int(text, 0)
        self.Skip.SetValue(f"0x{value:X}")
        return value

    @skip.setter
    def skip(self, value: int):
        value = value or 0
        self.Skip.SetValue(f"0x{value:X}")

    @property
    def length(self):
        text: str = self.Length.GetValue().strip() or "0"
        value = int(text, 0)
        self.Length.SetValue(f"0x{value:X}")
        return value

    @length.setter
    def length(self, value: int):
        value = value or 0
        self.Length.SetValue(f"0x{value:X}")

    def on_ports_updated(self, ports: List[Tuple[str, bool, str]]):
        user_port = self.port
        for port, is_usb, description in set(ports) - set(self.ports):
            info(f"Found new device: {description}")
            if user_port is None and is_usb:
                user_port = port
        for _, _, description in set(self.ports) - set(ports):
            info(f"Device unplugged: {description}")
        self.Port.Set([port[2] for port in ports])
        self.ports = ports
        self.port = user_port

    @on_event
    def on_browse_click(self):
        if self.operation == FlashOp.WRITE:
            title = "Open file"
            flags = wx.FD_OPEN | wx.FD_FILE_MUST_EXIST
        else:
            title = "Save file"
            flags = wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT
        init_dir = dirname(self.file) if self.file else os.getcwd()
        with wx.FileDialog(self, title, init_dir, style=flags) as dialog:
            dialog: wx.FileDialog
            if dialog.ShowModal() == wx.ID_CANCEL:
                return
            self.file = dialog.GetPath()
            self.OnUpdate()

    @only_target
    def on_start_click(self, button: wx.Button):
        info("Start click")
        self.DisableAll()
        enable_all = self.EnableAll

        class X(Thread):
            def run(self) -> None:
                with click.progressbar(length=0x200000) as bar:
                    for i in range(0x100):
                        bar.update(0x200000 // 0x100)
                        sleep(0.05)
                enable_all()

        X().start()

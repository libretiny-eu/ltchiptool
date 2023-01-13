#  Copyright (c) Kuba Szczodrzyński 2023-1-2.

import os
from enum import Enum
from logging import info
from os.path import dirname, isfile
from threading import Thread
from time import sleep

import click
import wx
import wx.adv
import wx.xrc

from ltchiptool import Family
from ltchiptool.commands.flash._utils import get_file_type
from ltchiptool.util import LoggingHandler, list_serial_ports, verbose
from uf2tool.models import UF2, Tag

from ._base import BasePanel
from ._utils import int_or_zero, on_event, only_target
from .work.ports import PortWatcher


class FlashOp(Enum):
    WRITE = "write"
    READ = "read"
    READ_ROM = "read_rom"


class FlashPanel(BasePanel):
    file_tuple: tuple | None = None
    ports: list[tuple[str, bool, str]]
    prev_read_full: bool = None

    delayed_port: str | None = None

    def __init__(self, res: wx.xrc.XmlResource, *args, **kw):
        super().__init__(*args, **kw)
        self.LoadXRC(res, "FlashPanel")

        self.ports = []

        self.Port = self.BindComboBox("combo_port")
        self.Rescan = self.BindButton("button_rescan", self.on_rescan_click)
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

        self.Baudrate = {
            None: self.BindRadioButton("radio_baudrate_auto"),
            115200: self.BindRadioButton("radio_baudrate_115200"),
            230400: self.BindRadioButton("radio_baudrate_230400"),
            460800: self.BindRadioButton("radio_baudrate_460800"),
            921600: self.BindRadioButton("radio_baudrate_921600"),
        }

        self.FileTypeText = self.FindStaticText("text_file_type")
        self.FileType = self.BindTextCtrl("input_file_type")
        self.Offset = self.BindTextCtrl("input_offset")
        self.SkipText = self.FindStaticText("text_skip")
        self.Skip = self.BindTextCtrl("input_skip")
        self.LengthText = self.FindStaticText("text_length")
        self.Length = self.BindTextCtrl("input_length")

        self.Offset.Bind(wx.EVT_KILL_FOCUS, self.OnBlur)
        self.Skip.Bind(wx.EVT_KILL_FOCUS, self.OnBlur)
        self.Length.Bind(wx.EVT_KILL_FOCUS, self.OnBlur)
        self.File.Bind(wx.EVT_KILL_FOCUS, self.OnBlur)

        self.Family.Set([f.description for f in Family.get_all() if f.name])

    def GetSettings(self) -> dict:
        return dict(
            port=self.port,
            baudrate=self.baudrate,
            operation=self.operation.value,
            auto_detect=self.auto_detect,
            family=self.family and self.family.short_name,
            file=self.file,
            offset=self.offset,
            skip=self.skip,
            length=self.length,
        )

    def SetSettings(
        self,
        port: str = None,
        baudrate: int = None,
        operation: str = FlashOp.WRITE.value,
        auto_detect: bool = True,
        family: str = None,
        file: str = None,
        offset: int = None,
        skip: int = None,
        length: int = None,
    ):
        self.port = port
        self.baudrate = baudrate
        self.operation = FlashOp(operation)
        self.auto_detect = auto_detect
        try:
            self.family = Family.get(short_name=family)
        except ValueError:
            self.family = None
        self.file = file
        self.offset = offset
        self.skip = skip
        self.length = length

    def OnShow(self):
        super().OnShow()
        self.start_work(PortWatcher(self.on_ports_updated))

    def OnUpdate(self, target: wx.Window = None):
        if target == self.Write:
            # perform file type detection again (in case of switching Read -> Write)
            self.file = self.file

        self.Family.Enable(self.operation != FlashOp.WRITE or not self.auto_detect)
        self.FileTypeText.Enable(self.operation == FlashOp.WRITE)
        self.FileType.Enable(self.operation == FlashOp.WRITE)
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
                is_uf2 = file_type and file_type.startswith("UF2")
                self.FileType.ChangeValue(file_type or "Unrecognized")
                self.AutoDetect.Enable(not is_uf2)
                if self.auto_detect:
                    self.family = family
                    self.offset = offset
                    self.skip = skip
                    self.length = length

                if is_uf2:
                    if not self.auto_detect:
                        self.auto_detect = True
                        self.OnUpdate()
                        return
                elif not file_type and self.auto_detect:
                    errors.append("File is unrecognized")
                elif not file_type:
                    warnings.append("Warning: file is unrecognized")
                    self.FileType.ChangeValue(file_type or "Raw")
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
                self.length = 0
            else:
                warnings.append("Using manual parameters")

        verbose(
            f"Update: read_full={self.read_full}, "
            f"target={type(target).__name__}, "
            f"port={self.port}, "
            f"family={self.family}",
        )

        if self.prev_read_full is not self.read_full:
            # switching "entire chip" reading - update input text
            self.length = self.length or 0x200000
            self.prev_read_full = self.read_full

        if not self.family:
            errors.append("Choose the chip family")
        if not self.length and not self.read_full:
            errors.append("Enter a correct length")
        if not self.port:
            errors.append("Choose a serial port")

        if errors:
            self.Start.SetNote(errors[0])
            self.Start.Disable()
        elif warnings:
            self.Start.SetNote(warnings[0])
            self.Start.Enable()
        else:
            self.Start.SetNote("")
            self.Start.Enable()

    def OnBlur(self, event: wx.FocusEvent):
        event.Skip()
        self.offset = self.offset
        self.skip = self.skip
        self.length = self.length
        self.file = self.file

    @property
    def port(self):
        if self.Port.GetSelection() == wx.NOT_FOUND:
            return None
        return self.ports[self.Port.GetSelection()][0]

    @port.setter
    def port(self, value: str | None):
        if value is None:
            self.Port.SetSelection(wx.NOT_FOUND)
        else:
            for port, _, description in self.ports:
                if value == port:
                    self.Port.SetValue(description)
                    self.DoUpdate(self.Port)
                    return
            self.delayed_port = value

    @property
    def baudrate(self):
        for baudrate, radio in self.Baudrate.items():
            if radio.GetValue():
                return baudrate
        return None

    @baudrate.setter
    def baudrate(self, value: int):
        for baudrate, radio in self.Baudrate.items():
            if baudrate == value:
                radio.SetValue(True)
                return

    @property
    def operation(self):
        if self.Write.GetValue():
            return FlashOp.WRITE
        if self.Read.GetValue():
            return FlashOp.READ
        if self.ReadROM.GetValue():
            return FlashOp.READ_ROM

    @operation.setter
    def operation(self, value: FlashOp):
        match value:
            case FlashOp.WRITE:
                self.Write.SetValue(True)
                self.DoUpdate(self.Write)
            case FlashOp.READ:
                self.Read.SetValue(True)
                self.DoUpdate(self.Read)
            case FlashOp.READ_ROM:
                self.ReadROM.SetValue(True)
                self.DoUpdate(self.ReadROM)

    @property
    def auto_detect(self):
        return self.AutoDetect.IsChecked()

    @auto_detect.setter
    def auto_detect(self, value: bool):
        self.AutoDetect.SetValue(value)
        self.DoUpdate(self.AutoDetect)

    @property
    def family(self):
        try:
            return Family.get(description=self.Family.GetValue())
        except ValueError:
            return None

    @family.setter
    def family(self, value: Family | None):
        self.Family.SetSelection(wx.NOT_FOUND)
        if value:
            self.Family.SetValue(value.description)
        self.DoUpdate(self.Family)

    @property
    def file(self):
        return self.File.GetValue()

    # noinspection PyTypeChecker
    @file.setter
    def file(self, value: str | None):
        value = value or ""
        self.File.ChangeValue(value)
        if self.operation != FlashOp.WRITE:
            return
        if not isfile(value):
            self.file_tuple = None
        else:
            with open(value, "rb") as f:
                tpl = get_file_type(None, f)
                if tpl[0] == "UF2":
                    try:
                        uf2 = UF2(f)
                        uf2.read(block_tags=False)
                        if Tag.FIRMWARE in uf2.tags and Tag.VERSION in uf2.tags:
                            firmware = uf2.tags[Tag.FIRMWARE].decode()
                            version = uf2.tags[Tag.VERSION].decode()
                            file_type = f"UF2 - {firmware} {version}"
                        elif Tag.BOARD in uf2.tags:
                            board = uf2.tags[Tag.BOARD].decode()
                            file_type = f"UF2 - {board}"
                        else:
                            file_type = "UF2"
                        family = uf2.family
                        tpl = tuple([file_type, family, *tpl[2:]])
                    except ValueError as e:
                        # catch UF2 parsing errors
                        LoggingHandler.get().emit_exception(e)
                        tpl = "Unrecognized UF2", None, None, None, None, 0
                self.file_tuple = tpl
        self.DoUpdate(self.File)

    @property
    def offset(self):
        text: str = self.Offset.GetValue().strip() or "0"
        value = int_or_zero(text)
        return value

    @offset.setter
    def offset(self, value: int):
        value = value or 0
        self.Offset.SetValue(f"0x{value:X}")

    @property
    def skip(self):
        text: str = self.Skip.GetValue().strip() or "0"
        value = int_or_zero(text)
        return value

    @skip.setter
    def skip(self, value: int):
        value = value or 0
        self.Skip.SetValue(f"0x{value:X}")

    @property
    def length(self):
        text: str = self.Length.GetValue().strip() or "0"
        value = int_or_zero(text)
        return value

    @length.setter
    def length(self, value: int | None):
        if self.read_full:
            self.Length.SetValue("Entire chip")
        else:
            self.Length.SetValue(f"0x{value:X}")

    @property
    def read_full(self):
        return self.length == 0 and self.auto_detect and self.operation != FlashOp.WRITE

    def on_ports_updated(self, ports: list[tuple[str, bool, str]]):
        user_port = self.port or self.delayed_port
        for port, is_usb, description in set(ports) - set(self.ports):
            info(f"Found new device: {description}")
            if user_port is None and is_usb:
                user_port = port
        for _, _, description in set(self.ports) - set(ports):
            info(f"Device unplugged: {description}")
        self.Port.Set([port[2] for port in ports])
        self.ports = ports
        self.port = user_port
        self.delayed_port = None

    @on_event
    def on_rescan_click(self):
        self.on_ports_updated(list_serial_ports())

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

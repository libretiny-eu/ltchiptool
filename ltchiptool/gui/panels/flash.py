#  Copyright (c) Kuba Szczodrzyński 2023-1-2.

import os
from datetime import datetime
from logging import debug, info
from os.path import dirname, isfile

import wx
import wx.adv
import wx.xrc

from ltchiptool import Family, SocInterface
from ltchiptool.gui.utils import int_or_zero, on_event, only_target, with_target
from ltchiptool.gui.work.flash import FlashThread
from ltchiptool.gui.work.ports import PortWatcher
from ltchiptool.util.cli import list_serial_ports
from ltchiptool.util.detection import Detection
from ltchiptool.util.fileio import chname
from ltchiptool.util.flash import FlashOp
from ltchiptool.util.logging import verbose

from .base import BasePanel


class FlashPanel(BasePanel):
    detection: Detection | None = None
    ports: list[tuple[str, bool, str]]
    prev_read_full: bool = None
    prev_file: str | None = None
    auto_file: str | None = None
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
        self.Cancel: wx.adv.CommandLinkButton = self.BindButton(
            "button_cancel", self.on_cancel_click
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

        self.File.Bind(wx.EVT_KILL_FOCUS, self.OnBlur)
        self.Cancel.SetNote("")

        families = set()
        family_codes = SocInterface.get_family_codes()
        for family in Family.get_all():
            if family.code in family_codes and family.description:
                families.add(family.description)
            if family.parent_code in family_codes:
                families.add(family.parent_description or family.description)
        self.Family.Set(sorted(families))

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
            prev_file=self.prev_file,
            auto_file=self.auto_file,
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
        prev_file: str = None,
        auto_file: str = None,
        **_,
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
        self.prev_file = prev_file
        self.auto_file = auto_file

    def OnShow(self):
        super().OnShow()
        self.start_work(PortWatcher(self.on_ports_updated))

    def OnUpdate(self, target: wx.Window = None):
        writing = self.operation == FlashOp.WRITE
        reading = not writing
        auto = self.auto_detect
        manual = not auto
        is_uf2 = self.detection is not None and self.detection.is_uf2
        need_offset = self.detection is not None and self.detection.need_offset

        match target:
            case (self.Read | self.ReadROM) if self.file:
                # generate a new filename for reading, to prevent
                # accidentally overwriting firmware files
                if not self.prev_file:
                    self.prev_file = self.file
                self.file = self.make_dump_filename()
            case self.Family if reading and self.file == self.auto_file:
                # regenerate the filename after changing family
                self.file = self.make_dump_filename()
            case self.Write:
                # restore filename previously used for writing
                if self.prev_file:
                    self.file = self.prev_file
                    self.prev_file = None
                # perform file type detection again (in case of switching Read -> Write)
                self.file = self.file

        self.Family.Enable(reading or manual)
        self.FileTypeText.Enable(writing)
        self.FileType.Enable(writing)
        self.Offset.Enable(manual or writing and need_offset)
        self.SkipText.Enable(writing)
        self.Skip.Enable(writing and manual)
        self.Length.Enable(manual)
        self.AutoDetect.Enable(reading or not is_uf2)

        errors = []
        warnings = []

        if writing:
            self.FileText.SetLabel("Input file")
            self.LengthText.SetLabel("Writing length")
            if not self.file:
                errors.append("Choose an input file")
            elif self.detection is None:
                errors.append("File does not exist")
            else:
                self.FileType.ChangeValue(self.detection.title)
                if manual and is_uf2:
                    self.auto_detect = auto = True
                if auto:
                    self.family = self.detection.family
                    if not need_offset:
                        self.offset = self.detection.offset
                    self.skip = self.detection.skip
                    self.length = self.detection.length

                match self.detection.type:
                    case Detection.Type.UNRECOGNIZED if auto:
                        errors.append("File is unrecognized")
                    case Detection.Type.UNRECOGNIZED:
                        warnings.append("Warning: file is unrecognized")
                    case Detection.Type.UNSUPPORTED:
                        errors.append("File is not directly flashable")
                    case Detection.Type.UNSUPPORTED_HERE:
                        errors.append(
                            f"File is not flashable to "
                            f"'{self.detection.family.description}'",
                        )
                    case Detection.Type.UNSUPPORTED_UF2:
                        errors.append("UF2 family unrecognized")
                    case Detection.Type.VALID_NEED_OFFSET:
                        warnings.append("Custom start offset needed")

                if manual:
                    warnings.append("Warning: using custom options")
        else:
            self.FileText.SetLabel("Output file")
            self.LengthText.SetLabel("Reading length")
            self.FileType.ChangeValue("")
            if not self.file:
                errors.append("Choose an output file")
            self.skip = 0
            if auto:
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

        self.Cancel.Disable()

    @with_target
    def OnBlur(self, event: wx.FocusEvent, target: wx.Window):
        event.Skip()
        if target == self.File:
            self.file = self.file

    @property
    def port(self):
        if not self.ports:
            return None
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
            return Family.get(description=self.Family.GetValue(), by_parent=True)
        except ValueError:
            return None

    @family.setter
    def family(self, value: Family | None):
        self.Family.SetSelection(wx.NOT_FOUND)
        if value:
            if value.description:
                self.Family.SetValue(value.description)
            if value.parent_description:
                self.Family.SetValue(value.parent_description)
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
        if self.detection and self.detection.name == value:
            return
        if not isfile(value):
            self.detection = None
        else:
            with open(value, "rb") as f:
                self.detection = Detection.perform(f)
        debug(f"Detection: {str(self.detection)}")
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
        value = value or 0
        if self.read_full:
            self.Length.SetValue("Entire chip")
        else:
            self.Length.SetValue(f"0x{value:X}")

    @property
    def read_full(self):
        return self.length == 0 and self.auto_detect and self.operation != FlashOp.WRITE

    def make_dump_filename(self):
        if not self.file:
            return
        date = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        rom = "_rom" if self.operation == FlashOp.READ_ROM else ""
        if self.family:
            filename = f"ltchiptool_{self.family.code}_{date}{rom}.bin"
        else:
            filename = f"ltchiptool_dump_{date}{rom}.bin"
        self.auto_file = chname(self.file, filename)
        verbose(f"Generated dump filename: {self.auto_file}")
        return self.auto_file

    def on_ports_updated(self, ports: list[tuple[str, bool, str]]):
        self.Port.Enable(not not ports)
        if not ports:
            self.ports = []
            self.Port.Set(["No serial ports found"])
            self.Port.SetSelection(0)
            return
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
            if self.operation != FlashOp.WRITE:
                # clear previous writing filename
                self.prev_file = None

    @on_event
    def on_start_click(self):
        if self.operation == FlashOp.WRITE and self.auto_detect and self.detection:
            soc = self.detection.soc or SocInterface.get(self.family)
            uf2 = self.detection.uf2
        else:
            soc = SocInterface.get(self.family)
            uf2 = None

        if self.operation != FlashOp.WRITE:
            if self.file == self.auto_file:
                self.file = self.make_dump_filename()
            if isfile(self.file):
                btn = wx.MessageBox(
                    message=f"File already exists. Do you want to overwrite it?",
                    caption="Warning",
                    style=wx.ICON_WARNING | wx.YES_NO,
                )
                if btn != wx.YES:
                    return

        work = FlashThread(
            port=self.port,
            baudrate=self.baudrate,
            operation=self.operation,
            file=self.file,
            soc=soc,
            offset=self.offset,
            skip=self.skip,
            length=self.length,
            verify=True,
            uf2=uf2,
            on_chip_info=self.Start.SetNote,
        )
        self.start_work(work, freeze_ui=True)
        self.Start.SetNote("")
        self.Cancel.Enable()

    @on_event
    def on_cancel_click(self):
        self.stop_work(FlashThread)

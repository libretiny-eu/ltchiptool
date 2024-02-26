#  Copyright (c) Kuba Szczodrzyński 2023-1-2.

import webbrowser
from logging import debug, info
from os.path import isfile
from pathlib import Path

import wx
import wx.xrc
from prettytable import PrettyTable

from ltchiptool import Family, SocInterface
from ltchiptool.gui.mixin.devices import DevicesBase
from ltchiptool.gui.mixin.file_dump import FileDumpBase
from ltchiptool.gui.utils import int_or_zero, on_event
from ltchiptool.gui.work.flash import FlashThread
from ltchiptool.util.detection import Detection
from ltchiptool.util.flash import FlashFeatures, FlashOp, format_flash_guide
from ltchiptool.util.logging import verbose


# noinspection PyPep8Naming
class FlashPanel(FileDumpBase, DevicesBase):
    detection: Detection | None = None
    ports: list[tuple[str, bool, str]]
    last_port: str | None = None
    chip_info: list[tuple[str, str]] | None = None

    def __init__(self, parent: wx.Window, frame):
        super().__init__(parent, frame)
        self.LoadXRC("FlashPanel")
        self.AddToNotebook("Flashing")

        self.ports = []

        self.Port = self.BindComboBox("combo_port")
        self.Rescan = self.BindButton("button_rescan", self.CallDeviceWatcher)
        self.Write = self.BindRadioButton("radio_write")
        self.Read = self.BindRadioButton("radio_read")
        self.ReadROM = self.BindRadioButton("radio_read_rom")
        self.ReadEfuse = self.BindRadioButton("radio_read_efuse")
        self.ReadInfo = self.BindRadioButton("radio_read_info")
        self.AutoDetect = self.BindCheckBox("checkbox_auto_detect")
        self.FileText = self.FindStaticText("text_file")
        self.File = self.BindTextCtrl("input_file")
        self.Family = self.BindComboBox("combo_family")
        self.Guide = self.BindButton("button_guide", self.OnGuideClick)
        self.Docs = self.BindButton("button_docs", self.OnDocsClick)
        self.Browse = self.BindButton("button_browse", self.OnBrowseClick)
        self.Start = self.BindCommandButton("button_start", self.OnStartClick)
        self.Cancel = self.BindCommandButton("button_cancel", self.OnCancelClick)

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

        self.Cancel.SetNote("")

        families = set()
        family_names = SocInterface.get_family_names()
        for family in Family.get_all():
            if family.name in family_names:
                families.add(family.description)
        self.Family.Set(sorted(families))

    def SetInitParams(self, file: str = None, **kwargs):
        super().SetInitParams(**kwargs)
        if file and isfile(file):
            self.operation = FlashOp.WRITE
            self.file = Path(file)

    def GetSettings(self) -> dict:
        return dict(
            port=self.port or self.last_port,
            baudrate=self.baudrate,
            operation=self.operation.value,
            auto_detect=self.auto_detect,
            family=self.family and self.family.name,
            offset=self.offset,
            skip=self.skip,
            length=self.length,
            **self.GetFileSettings(),
        )

    def SetSettings(
        self,
        port: str = None,
        baudrate: int = None,
        operation: str = FlashOp.WRITE.value,
        auto_detect: bool = True,
        family: str = None,
        offset: int = None,
        skip: int = None,
        length: int | None = None,
        **kwargs,
    ):
        self.port = port
        self.baudrate = baudrate
        self.operation = FlashOp(operation)
        self.auto_detect = auto_detect
        try:
            self.family = Family.get(name=family)
        except ValueError:
            self.family = None
        self.offset = offset
        self.skip = skip
        self.length = length
        self.SetFileSettings(**kwargs)

    def OnActivate(self):
        self.StartDeviceWatcher()

    def OnDeactivate(self):
        self.StopDeviceWatcher()

    def OnUpdate(self, target: wx.Window = None):
        if self.chip_info:
            chip_info = self.chip_info
            self.chip_info = None
            self.ShowChipInfo(chip_info)

        if self.IsAnyWorkRunning():
            return

        if target == self.Family:
            # update components based on SocInterface feature set
            soc = self.soc
            if soc:
                features = soc.flash_get_features()
                guide = soc.flash_get_guide()
                docs = soc.flash_get_docs_url()
            else:
                features = FlashFeatures()
                guide = None
                docs = None
            self.Write.Enable(features.can_write)
            self.Read.Enable(features.can_read)
            self.ReadROM.Enable(features.can_read_rom)
            self.ReadEfuse.Enable(features.can_read_efuse)
            self.ReadInfo.Enable(features.can_read_info)
            self.Guide.Enable(bool(guide))
            self.Docs.Enable(bool(docs))
            if not features.can_write and self.Write.GetValue():
                self.Read.SetValue(True)
            if not features.can_read and self.Read.GetValue():
                self.Write.SetValue(True)
            if not features.can_read_rom and self.ReadROM.GetValue():
                self.Read.SetValue(True)
            if not features.can_read_efuse and self.ReadEfuse.GetValue():
                self.Read.SetValue(True)
            if not features.can_read_info and self.ReadInfo.GetValue():
                self.Read.SetValue(True)

        writing = self.operation == FlashOp.WRITE
        reading = not writing
        reading_info = self.operation == FlashOp.READ_INFO

        is_uf2 = self.detection is not None and self.detection.is_uf2
        need_offset = self.detection is not None and self.detection.need_offset

        force_auto = (writing and is_uf2) or reading_info
        auto = self.auto_detect
        manual = not auto
        if manual and force_auto:
            self.auto_detect = auto = True
            manual = False

        match target:
            case self.Read | self.ReadROM | self.ReadEfuse if self.file:
                # generate a new filename for reading, to prevent
                # accidentally overwriting firmware files
                self.generate_read_filename()
            case self.Family if reading:
                # regenerate the filename after changing family
                self.regenerate_read_filename()
            case self.Write:
                # restore filename previously used for writing
                # perform file type detection again (in case of switching Read -> Write)
                self.restore_write_filename()

        self.Family.Enable(reading or manual)
        self.FileTypeText.Enable(writing)
        self.FileType.Enable(writing)
        self.Offset.Enable(manual or writing and need_offset)
        self.SkipText.Enable(writing)
        self.Skip.Enable(writing and manual)
        self.Length.Enable(manual)
        self.AutoDetect.Enable(not force_auto)
        self.File.Enable(not reading_info)
        self.Browse.Enable(not reading_info)

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
                if self.offset % 0x1000:
                    errors.append(f"Offset (0x{self.offset:X}) is not 4 KiB-aligned")
                if auto:
                    self.family = self.detection.family
                    if not need_offset:
                        self.offset = self.detection.offset
                    self.skip = self.detection.skip
                    self.length = None if is_uf2 else self.detection.length

                match self.detection.type:
                    case Detection.Type.UNRECOGNIZED if auto:
                        errors.append("File is unrecognized")
                    case Detection.Type.UNRECOGNIZED:
                        warnings.append("Warning: file is unrecognized")
                    case Detection.Type.UNSUPPORTED if auto:
                        errors.append("File is not directly flashable")
                    case Detection.Type.UNSUPPORTED_HERE if auto:
                        errors.append(
                            f"File is not flashable to "
                            f"'{self.detection.family.description}'",
                        )
                    case Detection.Type.UNSUPPORTED_UF2:
                        errors.append("UF2 family unrecognized")
                    case Detection.Type.VALID_NEED_OFFSET:
                        warnings.append("Custom start offset needed")
                    case Detection.Type.UNSUPPORTED | Detection.Type.UNSUPPORTED_HERE:
                        warnings.append("Warning: file shouldn't be directly flashed")

                if manual:
                    warnings.append("Warning: using custom options")
                    if self.skip >= self.detection.size:
                        errors.append(
                            f"Skip offset (0x{self.skip:X}) "
                            f"not within input file bounds "
                            f"(0x{self.detection.size:X})"
                        )
                    elif self.skip + (self.length or 0) > self.detection.size:
                        errors.append(
                            f"Writing length (0x{self.skip:X} + 0x{self.length:X}) "
                            f"not within input file bounds "
                            f"(0x{self.detection.size:X})"
                        )
                        errors.append("")

        else:
            self.FileText.SetLabel("Output file")
            self.LengthText.SetLabel("Reading length")
            self.FileType.ChangeValue("")
            if not self.file and not reading_info:
                errors.append("Choose an output file")
            self.skip = 0
            if auto:
                self.offset = 0
                self.length = 0
            else:
                warnings.append("Using manual parameters")

        verbose(
            f"Update: "
            f"target={type(target).__name__}, "
            f"port={self.port}, "
            f"family={self.family}",
        )

        if not self.family:
            errors.append("Choose the chip family")
        if self.length == 0:
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

    def EnableAll(self):
        super().EnableAll()
        self.DoUpdate(self.Family)

    def OnFileChanged(self, path: Path = None) -> bool | None:
        if self.IsAnyWorkRunning():
            return False
        if self.operation != FlashOp.WRITE:
            return
        if self.detection and self.detection.name == str(path):
            return
        if not (path and path.is_file()):
            self.detection = None
        else:
            with path.open("rb") as f:
                self.detection = Detection.perform(f)
        debug(f"Detection: {str(self.detection)}")

    @property
    def filename_stem(self) -> str:
        return self.family and self.family.code or "dump"

    @property
    def filename_tags(self) -> str:
        rom = "_rom" if self.operation == FlashOp.READ_ROM else ""
        efuse = "_efuse" if self.operation == FlashOp.READ_EFUSE else ""
        return rom + efuse

    @property
    def is_reading(self) -> bool:
        return self.operation in [FlashOp.READ, FlashOp.READ_ROM, FlashOp.READ_EFUSE]

    @property
    def is_writing(self) -> bool:
        return self.operation == FlashOp.WRITE

    def set_writing(self) -> None:
        if self.IsAnyWorkRunning():
            return
        self.operation = FlashOp.WRITE

    @property
    def port(self):
        if not self.ports:
            return None
        if self.Port.GetSelection() == wx.NOT_FOUND:
            return None
        try:
            return self.ports[self.Port.GetSelection()][0]
        except IndexError:
            return None

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
            self.last_port = value
        self.DoUpdate(self.Port)

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
        if self.ReadEfuse.GetValue():
            return FlashOp.READ_EFUSE
        if self.ReadInfo.GetValue():
            return FlashOp.READ_INFO

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
            case FlashOp.READ_EFUSE:
                self.ReadEfuse.SetValue(True)
                self.DoUpdate(self.ReadEfuse)
            case FlashOp.READ_INFO:
                self.ReadInfo.SetValue(True)
                self.DoUpdate(self.ReadInfo)

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
            for family in value.inheritance:
                self.Family.SetValue(family.description)
        self.DoUpdate(self.Family)

    @property
    def soc(self) -> SocInterface | None:
        if not self.family:
            return None
        if self.operation == FlashOp.WRITE and self.auto_detect and self.detection:
            return self.detection.soc or SocInterface.get(self.family)
        else:
            return SocInterface.get(self.family)

    @property
    def offset(self) -> int:
        text: str = self.Offset.GetValue().strip() or "0"
        value = int_or_zero(text)
        return value

    @offset.setter
    def offset(self, value: int) -> None:
        value = value or 0
        self.Offset.SetValue(f"0x{value:X}")

    @property
    def skip(self) -> int:
        text: str = self.Skip.GetValue().strip() or "0"
        value = int_or_zero(text)
        return value

    @skip.setter
    def skip(self, value: int) -> None:
        value = value or 0
        self.Skip.SetValue(f"0x{value:X}")

    @property
    def length(self) -> int | None:
        text: str = self.Length.GetValue().strip()
        if not text:
            return None
        value = int_or_zero(text)
        return value

    @length.setter
    def length(self, value: int | None):
        if value:
            self.Length.SetValue(f"0x{value:X}")
        else:
            self.Length.SetValue("")

    def OnPortsUpdated(self, ports: list[tuple[str, bool, str]]):
        user_port = self.port
        auto_port = None

        for port, is_usb, description in set(ports) - set(self.ports):
            info(f"Found new device: {description}")
            if is_usb and not auto_port:
                auto_port = port
        for _, _, description in set(self.ports) - set(ports):
            info(f"Device unplugged: {description}")

        if not self.IsAnyWorkRunning():
            self.Port.Enable(bool(ports))
        if ports:
            self.Port.Set([port[2] for port in ports])
            self.ports = ports
            self.port = user_port or auto_port or self.last_port
        else:
            self.Port.Set(["No serial ports found"])
            self.Port.SetSelection(0)
            self.ports = []
            self.DoUpdate(self.Port)

    def OnChipInfoFull(self, chip_info: list[tuple[str, str]]):
        self.chip_info = chip_info

    def ShowChipInfo(self, chip_info: list[tuple[str, str]]):
        table = PrettyTable()
        table.field_names = ["Name", "Value"]
        table.align = "l"
        for key, value in chip_info:
            table.add_row([key, value])
        self.MessageDialogMonospace(
            message=table.get_string(),
            caption="Chip info",
        )

    @on_event
    def OnGuideClick(self):
        guide = self.soc.flash_get_guide()
        if not guide:
            self.Guide.Disable()
            return
        self.MessageDialogMonospace(
            message="\n".join(format_flash_guide(self.soc)),
            caption="Flashing guide",
        )

    @on_event
    def OnDocsClick(self):
        docs = self.soc.flash_get_docs_url()
        if not docs:
            self.Docs.Disable()
            return
        webbrowser.open_new_tab(docs)

    @on_event
    def OnStartClick(self):
        soc = self.soc

        if self.is_reading:
            self.regenerate_read_filename()
            if self.file.is_file():
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
            file=self.file and str(self.file) or "",
            soc=soc,
            offset=self.offset,
            skip=self.skip,
            length=self.length,
            verify=True,
            ctx=self.detection and self.detection.get_uf2_ctx(),
            on_chip_info_summary=self.Start.SetNote,
            on_chip_info_full=self.OnChipInfoFull,
        )
        self.StartWork(work)
        self.Start.SetNote("")
        self.Cancel.Enable()

    @on_event
    def OnCancelClick(self):
        self.StopWork(FlashThread)

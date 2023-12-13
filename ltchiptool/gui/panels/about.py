#  Copyright (c) Kuba Szczodrzyński 2023-1-16.

import sys
from os.path import dirname, join

import wx.xrc

from ltchiptool.util.ltim import LTIM
from ltchiptool.util.lvm import LVM, LVMPlatform

from .base import BasePanel


class AboutPanel(BasePanel):
    def __init__(self, parent: wx.Window, frame):
        super().__init__(parent, frame)
        self.LoadXRC("AboutPanel")
        self.AddToNotebook("About")

        platform = LVM.default()
        lt_path = platform.path
        lt_version = f"v{platform.version}"
        if platform.type == LVMPlatform.Type.SNAPSHOT:
            lt_path_title = "Local data snapshot path"
            lt_version = None
        else:
            lt_path_title = "LibreTiny package path"

        python = ".".join(str(i) for i in sys.version_info[:3])
        python += f" ({sys.executable})"

        if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
            logo = join(sys._MEIPASS, "ltchiptool-192x192.png")
            with open(join(sys._MEIPASS, "ltchiptool.txt"), "r") as f:
                build_date = f.read()
        else:
            logo = join(dirname(__file__), "..", "ltchiptool-192x192.png")
            build_date = None

        self.FindStaticText("text_lt_version").SetLabel(lt_version or "-")
        self.FindStaticText("text_tool_version").SetLabel(
            LTIM.get_version_full() or "-"
        )
        if build_date:
            self.FindStaticText("text_build_date").SetLabel(build_date)
        else:
            self.FindStaticText("text_build_date_title").Hide()
            self.FindStaticText("text_build_date").Hide()
        self.FindStaticText("text_path_title").SetLabel(lt_path_title)
        path = self.BindHyperlinkCtrl("text_path")
        path.SetLabel(lt_path)
        path.SetURL(lt_path)
        self.FindStaticText("text_python").SetLabel(python or "-")

        bitmap = self.FindStaticBitmap("bmp_logo")
        size = bitmap.GetSize().y
        image = wx.Image(logo)
        image.Rescale(size, size)
        bitmap.SetBitmap(image)

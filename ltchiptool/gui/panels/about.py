#  Copyright (c) Kuba Szczodrzyński 2023-1-16.

import json
import sys
from os.path import abspath, dirname, join

import wx.adv
import wx.xrc

from ltchiptool import get_version
from ltchiptool.util.env import lt_find_json, lt_find_path

from .base import BasePanel


class AboutPanel(BasePanel):
    def __init__(self, res: wx.xrc.XmlResource, *args, **kw):
        super().__init__(*args, **kw)
        self.LoadXRC(res, "AboutPanel")

        lt_version = None
        lt_path_title = ""
        lt_path = ""

        try:
            lt_find_path()
            platform = lt_find_json("platform.json")
            platform = abspath(platform)
        except FileNotFoundError:
            platform = None
        try:
            families = lt_find_json("families.json")
            families = abspath(families)
        except FileNotFoundError:
            families = None

        if platform:
            lt_path_title = "LibreTuya package path"
            lt_path = dirname(platform)
            with open(platform, "r") as f:
                platform = json.load(f)
                version = platform.get("version", None)
                lt_version = version and f"v{version}"
        elif families:
            lt_path_title = "Local data snapshot path"
            lt_path = dirname(families)

        tool_version = "v" + get_version()
        if "site-packages" not in __file__ and not hasattr(sys, "_MEIPASS"):
            tool_version += " (dev)"

        if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
            logo = join(sys._MEIPASS, "ltchiptool-192x192.png")
            with open(join(sys._MEIPASS, "ltchiptool.txt"), "r") as f:
                build_date = f.read()
        else:
            logo = join(dirname(__file__), "..", "ltchiptool-192x192.png")
            build_date = None

        self.FindStaticText("text_lt_version").SetLabel(lt_version or "-")
        self.FindStaticText("text_tool_version").SetLabel(tool_version or "-")
        if build_date:
            self.FindStaticText("text_build_date").SetLabel(build_date)
        else:
            self.FindStaticText("text_build_date_title").Hide()
            self.FindStaticText("text_build_date").Hide()
        self.FindStaticText("text_path_title").SetLabel(lt_path_title)
        path: wx.adv.HyperlinkCtrl = self.FindStaticText("text_path")
        path.SetLabel(lt_path)
        path.SetURL(lt_path)

        bitmap = self.FindStaticBitmap("bmp_logo")
        size = bitmap.GetSize().y
        image = wx.Image(logo)
        image.Rescale(size, size)
        bitmap.SetBitmap(image)

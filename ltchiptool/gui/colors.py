#  Copyright (c) Kuba Szczodrzyński 2023-5-22.

import json
import sys
from os.path import dirname, join

import wx


class ColorPalette:
    INSTANCE: "ColorPalette" = None
    COLORS_JSON: dict[str, dict] = None
    COLORS_NAME = [
        "black",
        "red",
        "green",
        "yellow",
        "blue",
        "magenta",
        "cyan",
        "white",
        "bright_black",
        "bright_red",
        "bright_green",
        "bright_yellow",
        "bright_blue",
        "bright_magenta",
        "bright_cyan",
        "bright_white",
    ]
    name: str
    title: str
    colors: list[wx.Colour]

    def __init__(self, name: str = None):
        self.load_colors()
        if name not in ColorPalette.COLORS_JSON:
            titles = self.get_titles()
            if name in titles:
                name = self.get_names()[titles.index(name)]
            else:
                name = "windows10"
        palette = ColorPalette.COLORS_JSON[name]
        self.name = name
        self.title = palette["title"]
        self.colors = []
        for name in ColorPalette.COLORS_NAME:
            color: str = palette["colors"][name]
            if color.startswith("#"):
                self.colors.append(wx.Colour(color))
            elif "," in color:
                self.colors.append(wx.Colour(*map(int, color.split(","))))

    @staticmethod
    def load_colors() -> None:
        if not ColorPalette.COLORS_JSON:
            if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
                colors = join(sys._MEIPASS, "colors.json")
            else:
                colors = join(dirname(__file__), "colors.json")
            with open(colors, "r") as f:
                ColorPalette.COLORS_JSON = json.load(f)

    @staticmethod
    def get() -> "ColorPalette":
        if ColorPalette.INSTANCE:
            return ColorPalette.INSTANCE
        ColorPalette.INSTANCE = ColorPalette()
        return ColorPalette.INSTANCE

    @staticmethod
    def set(instance: "ColorPalette") -> "ColorPalette":
        ColorPalette.INSTANCE = instance
        return instance

    @staticmethod
    def get_names() -> list[str]:
        ColorPalette.load_colors()
        return list(ColorPalette.COLORS_JSON.keys())

    @staticmethod
    def get_titles() -> list[str]:
        ColorPalette.load_colors()
        return [p["title"] for p in ColorPalette.COLORS_JSON.values()]

    def get_color_name(self, value: wx.Colour) -> str | None:
        try:
            i = self.colors.index(value)
            return self.COLORS_NAME[i]
        except ValueError:
            return None

    def __getitem__(self, item: str | int) -> wx.Colour:
        if isinstance(item, int):
            return self.colors[item]
        if item in ColorPalette.COLORS_NAME:
            return self.colors[ColorPalette.COLORS_NAME.index(item)]
        return wx.WHITE

    @property
    def background(self) -> wx.Colour:
        return self.colors[0]

    @property
    def foreground(self) -> wx.Colour:
        return self.colors[-1]

    def apply(
        self,
        ctrl: wx.TextCtrl,
        old: "ColorPalette" = None,
    ) -> None:
        start = 0
        attr = wx.TextAttr()
        if old:
            for num in range(ctrl.GetNumberOfLines()):
                # fetch line text
                line: str = ctrl.GetLineText(num)
                # calculate line start and end
                end = start + len(line) + 1
                # get current text style
                ctrl.GetStyle(start, attr)
                # find old color name
                color = old.get_color_name(attr.GetTextColour())
                # set new color name
                attr.SetTextColour(self[color])
                # apply the new style
                ctrl.SetStyle(start, end, attr)
                # increment char counter
                start = end
        # set background color
        ctrl.SetBackgroundColour(self.background)

# -*- mode: python ; coding: utf-8 -*-

from pkgutil import iter_modules

from PyInstaller.utils.hooks import collect_data_files

import ltctplugin

hiddenimports = [
    name
    for _, name, _ in iter_modules(ltctplugin.__path__, ltctplugin.__name__ + ".")
    if name != "ltctplugin.base"
]

datas = []

for module in hiddenimports:
    datas += collect_data_files(module)

# noinspection PyUnresolvedReferences
a = Analysis(
    ["gui.py"],
    datas=[
        ("ltchiptool.txt", "."),
        ("ltchiptool/boards/", "./boards/"),
        ("ltchiptool/platform.json", "."),
        ("ltchiptool/families.json", "."),
        ("ltchiptool/gui/res/ltchiptool-192x192.png", "."),
        ("ltchiptool/gui/res/ltchiptool.ico", "."),
        ("ltchiptool/gui/res/ltchiptool.xrc", "."),
        ("ltchiptool/gui/res/ko-fi.png", "."),
        ("ltchiptool/gui/res/colors.json", "."),
        ("pyproject.toml", "."),
    ]
    + datas,
    hiddenimports=hiddenimports,
    runtime_hooks=[
        "ltchiptool/gui/res/sitecustomize.py",
    ],
)

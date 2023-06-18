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

a = Analysis(
    ["gui.py"],
    datas=[
        ("ltchiptool.txt", "."),
        ("ltchiptool/boards/", "./boards/"),
        ("ltchiptool/platform.json", "."),
        ("ltchiptool/families.json", "."),
        ("ltchiptool/gui/ltchiptool-192x192.png", "."),
        ("ltchiptool/gui/ltchiptool.ico", "."),
        ("ltchiptool/gui/ltchiptool.xrc", "."),
        ("ltchiptool/gui/colors.json", "."),
        ("pyproject.toml", "."),
    ]
    + datas,
    hiddenimports=hiddenimports,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    name="ltchiptool",
    strip=False,
    upx=True,
    console=False,
    icon=["ltchiptool\\gui\\ltchiptool.ico"],
    version="gui-win32.txt",
)

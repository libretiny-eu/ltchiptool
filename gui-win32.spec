# -*- mode: python ; coding: utf-8 -*-

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
        ("pyproject.toml", "."),
    ],
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

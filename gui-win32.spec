# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ["gui.py"],
    datas=[
        ("ltchiptool/gui/ltchiptool.xrc", "."),
        ("ltchiptool/boards/", "./boards/"),
        ("ltchiptool/families.json", "."),
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
    version="gui-win32.txt",
)

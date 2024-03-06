# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo,
    StringFileInfo,
    StringStruct,
    StringTable,
    VarFileInfo,
    VarStruct,
    VSVersionInfo,
)

# noinspection PyUnresolvedReferences
pyz = PYZ(a.pure, a.zipped_data)

# noinspection PyUnresolvedReferences
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
    icon=["ltchiptool\\gui\\res\\ltchiptool.ico"],
    version=VSVersionInfo(
        ffi=FixedFileInfo(
            filevers=(0, 0, 0, 0),
            prodvers=(0, 0, 0, 0),
            mask=0x3F,
            flags=0x0,
            OS=0x40004,
            fileType=0x1,
            subtype=0x0,
            date=(0, 0),
        ),
        kids=[
            # fmt: off
            StringFileInfo([StringTable("040904B0", [
                StringStruct("CompanyName", "kuba2k2"),
                StringStruct("FileDescription", "--description--"),
                StringStruct("FileVersion", "0.0.0"),
                StringStruct("InternalName", "ltchiptool"),
                StringStruct("LegalCopyright", "© 2023 Kuba Szczodrzyński."),
                StringStruct("OriginalFilename", "ltchiptool-v0.0.0.exe"),
                StringStruct("ProductName", "ltchiptool"),
                StringStruct("ProductVersion", "0.0.0"),
            ])]),
            # fmt: on
            VarFileInfo([VarStruct("Translation", [1033, 1200])]),
        ],
    ),
)

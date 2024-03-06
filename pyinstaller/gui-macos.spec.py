# -*- mode: python ; coding: utf-8 -*-

# noinspection PyUnresolvedReferences
pyz = PYZ(a.pure)

# noinspection PyUnresolvedReferences
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ltchiptool",
    strip=False,
    upx=True,
    console=False,
)

# noinspection PyUnresolvedReferences
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="ltchiptool",
)

# noinspection PyUnresolvedReferences
app = BUNDLE(
    coll,
    name="ltchiptool.app",
    icon="ltchiptool/gui/res/ltchiptool-192x192.png",
    bundle_identifier=None,
    version="0.0.0",
    info_plist={
        "NSPrincipalClass": "NSApplication",
        "NSAppleScriptEnabled": False,
    },
)

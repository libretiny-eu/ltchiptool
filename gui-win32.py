#  Copyright (c) Kuba Szczodrzyński 2023-1-14.

if __name__ == "__main__":
    import re
    from os import rename

    import PyInstaller.__main__

    from ltchiptool.version import get_description, get_version

    version = get_version()
    version_tuple = ", ".join(re.sub(r"[^\d.]", "", version).split("."))
    description = get_description()

    with open(__file__, "r") as f:
        code = f.read()
        _, _, code = code.partition("exit" + "()")
        code = code.replace("0.0.0", version)
        code = code.replace("0, 0, 0", version_tuple)
        code = code.replace("--description--", description)
    with open(__file__.replace(".py", ".txt"), "w") as f:
        f.write(code.strip())

    PyInstaller.__main__.run([__file__.replace(".py", ".spec")])

    rename("dist/ltchiptool.exe", f"dist/ltchiptool-v{version}.exe")

    exit()

# noinspection PyUnresolvedReferences
VSVersionInfo(
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
)

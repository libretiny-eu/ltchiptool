#  Copyright (c) Kuba Szczodrzyński 2023-1-14.

if __name__ == "__main__":
    import re
    import socket
    from datetime import datetime
    from os import rename, unlink
    from os.path import isfile
    from shutil import SameFileError, copy

    import PyInstaller.__main__

    from ltchiptool.util.lvm import LVM

    with open("pyproject.toml", "r", encoding="utf-8") as f:
        text = f.read()
        version = re.search(r"version\s?=\s?\"(.+?)\"", text).group(1)
        version_raw = re.search(r"(\d+\.\d+\.\d+)", version).group(1)
        version_tuple = ", ".join(version_raw.split("."))
        description = re.search(r"description\s?=\s?\"(.+?)\"", text).group(1)

    try:
        lvm = LVM.get()
        lvm.require_version()
        platform = lvm.find_json("platform.json", version=True)
        families = lvm.find_json("families.json", version=True)
        copy(platform, "ltchiptool/platform.json")
        copy(families, "ltchiptool/families.json")
    except (FileNotFoundError, SameFileError):
        # ignore if LT is not installed; fall back to locally available files
        pass

    if not (isfile("ltchiptool/platform.json") and isfile("ltchiptool/families.json")):
        raise FileNotFoundError("Data files are missing")

    with open(__file__, "r") as f:
        code = f.read()
        _, _, code = code.partition("exit" + "()")
        code = code.replace("0.0.0", version)
        code = code.replace("0, 0, 0", version_tuple)
        code = code.replace("--description--", description)
    with open(__file__.replace(".py", ".txt"), "w") as f:
        f.write(code.strip())
    with open("ltchiptool.txt", "w") as f:
        date = datetime.now().strftime("%Y-%m-%d")
        f.write(f"{date} @ {socket.gethostname()}")

    PyInstaller.__main__.run([__file__.replace(".py", ".spec")])

    if isfile(f"dist/ltchiptool-v{version}.exe"):
        unlink(f"dist/ltchiptool-v{version}.exe")
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

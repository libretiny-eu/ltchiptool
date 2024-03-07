#  Copyright (c) Kuba Szczodrzyński 2023-1-14.

if __name__ == "__main__":
    import re
    import socket
    from datetime import datetime
    from os import getcwd, makedirs, rename, unlink
    from os.path import isdir, isfile
    from pathlib import Path
    from shutil import SameFileError, copy, copytree, rmtree

    import PyInstaller.__main__

    from ltchiptool.util.ltim import LTIM
    from ltchiptool.util.lvm import LVM

    root_path = Path(__file__).parent.resolve()
    cwd_path = Path(getcwd()).resolve()
    if cwd_path != root_path:
        raise ValueError(
            f"Must be executed in ltchiptool root directory "
            f"(CWD: '{cwd_path}', root: '{root_path}'"
        )

    # read version and project description from pyproject.toml
    with open("pyproject.toml", "r", encoding="utf-8") as f:
        text = f.read()
        version = re.search(r"version\s?=\s?\"(.+?)\"", text).group(1)
        version_raw = re.search(r"(\d+\.\d+\.\d+)", version).group(1)
        version_tuple = ", ".join(version_raw.split("."))
        description = re.search(r"description\s?=\s?\"(.+?)\"", text).group(1)

    # copy local data snapshot from LibreTiny platform
    try:
        lvm = LVM.get()
        lvm.require_version()
        platform = lvm.find_json("platform.json", version=True)
        families = lvm.find_json("families.json", version=True)
        copy(platform, "ltchiptool/platform.json")
        copy(families, "ltchiptool/families.json")
        makedirs("ltchiptool/boards/", exist_ok=True)
        boards = Path(lvm.path(), "boards")
        for board in boards.glob("*.json"):
            copy(board, f"ltchiptool/boards/{board.name}")
        rmtree("ltchiptool/boards/_base/")
        copytree(boards / "_base", "ltchiptool/boards/_base/")
    except (FileNotFoundError, SameFileError):
        # ignore if LT is not installed; fall back to locally available files
        pass

    if not (isfile("ltchiptool/platform.json") and isfile("ltchiptool/families.json")):
        raise FileNotFoundError("Data files are missing")
    if not isdir("ltchiptool/boards/"):
        raise FileNotFoundError("Boards directory is missing")

    # get platform spec file
    ltim = LTIM.get()
    res_path = root_path / "ltchiptool" / "gui" / "res"
    spec_base_path = res_path / f"gui.spec.py"
    spec_plat_path = res_path / f"gui-{ltim.platform}.spec.py"
    spec_path = root_path / f"gui-{ltim.platform}.spec"
    if not spec_plat_path.is_file():
        raise FileNotFoundError(
            f"GUI build not supported on platform '{ltim.platform}' "
            f"(file '{spec_plat_path}' not found)"
        )

    # process the PyInstaller spec file
    spec = spec_base_path.read_text()
    spec += spec_plat_path.read_text()
    spec = spec.replace("0.0.0", version)
    spec = spec.replace("0, 0, 0", version_tuple)
    spec = spec.replace("--description--", description)
    # write it back without the .py extension
    spec_path.write_text(spec.strip())

    # write build date
    with open("ltchiptool.txt", "w") as f:
        date = datetime.now().strftime("%Y-%m-%d")
        f.write(f"{date} @ {socket.gethostname()}")

    # cleanup dist files
    if isfile(f"dist/ltchiptool-v{version}.exe"):
        unlink(f"dist/ltchiptool-v{version}.exe")
    if isdir(f"dist/ltchiptool/"):
        rmtree(f"dist/ltchiptool/")
    if isdir(f"dist/ltchiptool.app/"):
        rmtree(f"dist/ltchiptool.app/")

    # run PyInstaller
    PyInstaller.__main__.run([str(spec_path)])

    # rename the resulting executable
    if ltim.is_windows():
        rename("dist/ltchiptool.exe", f"dist/ltchiptool-v{version}.exe")

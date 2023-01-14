# Copyright (c) Kuba Szczodrzyński 2022-07-29.

import json
import sys
from os.path import dirname, expanduser, isdir, isfile, join
from typing import Dict, Union

LT_PATH: Union[str, None] = None
LT_JSON_CACHE: Dict[str, dict] = {}


def lt_set_path(path: str) -> None:
    global LT_PATH
    if isfile(join(path, "families.json")) and isdir(join(path, "boards")):
        LT_PATH = path


def lt_find_path() -> str:
    global LT_PATH
    if LT_PATH and isdir(LT_PATH):
        return LT_PATH
    # try to import PIO modules first
    try:
        from platformio.package.manager.platform import PlatformPackageManager

        manager = PlatformPackageManager()
        pkg = manager.get_package("libretuya")
        LT_PATH = pkg.path
        return pkg.path
    except (ImportError, AttributeError):
        pass
    # search cwd and default PIO path
    paths = [
        ".",
        expanduser("~/.platformio/platforms/libretuya"),
    ]
    for path in paths:
        if isfile(join(path, "families.json")) and isdir(join(path, "boards")):
            LT_PATH = path
            return path
    raise FileNotFoundError(
        "Couldn't find LibreTuya directory. "
        "Either install PlatformIO with LibreTuya "
        "package, or execute this command in LT directory."
    )


def lt_find_json(name: str) -> str:
    try:
        path = join(lt_find_path(), name)
        if isfile(path):
            return path
    except FileNotFoundError as e:
        # LT can't be found, fallback to local copies
        if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
            path = join(sys._MEIPASS, name)
        else:
            path = join(dirname(__file__), "..", name)

        if not isfile(path):
            # no local copy, raise the original exception
            raise e
        return path
    # LT found, but no file by that name exists
    raise FileNotFoundError(path)


def lt_read_json(name: str) -> Union[dict, list]:
    global LT_JSON_CACHE
    if name not in LT_JSON_CACHE:
        path = lt_find_json(name)
        with open(path, "rb") as f:
            LT_JSON_CACHE[name] = json.load(f)
    return LT_JSON_CACHE[name]

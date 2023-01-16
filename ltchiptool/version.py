# Copyright (c) Kuba Szczodrzyński 2022-08-03.

import re
import sys
from os.path import dirname, isfile, join
from typing import Optional

from importlib_metadata import PackageNotFoundError, version


def get_version() -> Optional[str]:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        pyproject = join(sys._MEIPASS, "pyproject.toml")
    else:
        pyproject = join(dirname(__file__), "..", "pyproject.toml")

    if isfile(pyproject):
        with open(pyproject, "r", encoding="utf-8") as f:
            text = f.read()
            ver = re.search(r"version\s?=\s?\"(.+?)\"", text)
            if ver:
                return ver.group(1)
    try:
        return version("ltchiptool")
    except PackageNotFoundError:
        return None

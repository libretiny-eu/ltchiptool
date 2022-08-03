# Copyright (c) Kuba Szczodrzyński 2022-08-03.

import re
from os.path import dirname, isfile, join
from typing import Optional

from importlib_metadata import PackageNotFoundError, version


def get_version() -> Optional[str]:
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

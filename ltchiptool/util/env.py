# Copyright (c) Kuba Szczodrzyński 2022-07-29.

from os.path import isdir, isfile, join
from typing import Dict, Union

LT_PATH: Union[str, None] = None
LT_JSON_CACHE: Dict[str, dict] = {}


def lt_set_path(path: str) -> None:
    global LT_PATH
    if isfile(join(path, "families.json")) and isdir(join(path, "boards")):
        LT_PATH = path

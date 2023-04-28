# Copyright (c) Kuba Szczodrzyński 2022-07-29.

from os.path import isdir, isfile, join

from .lvm import LVM


def lt_set_path(path: str) -> None:
    if isfile(join(path, "families.json")) and isdir(join(path, "boards")):
        LVM.add_path(path)

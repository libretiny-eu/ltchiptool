# Copyright (c) Kuba Szczodrzyński 2022-07-29.

from ltchiptool.models import Family

from .interface import SocInterface

__all__ = [
    "SocInterface",
    "get_soc",
]


def get_soc(family: Family) -> SocInterface:
    if family.parent_code == "bk72xx":
        from .bk72xx import BK72XXMain

        return BK72XXMain()
    if family.code == "ambz":
        from .ambz import AmebaZMain

        return AmebaZMain()
    raise NotImplementedError(f"Unsupported family - {family.name}")

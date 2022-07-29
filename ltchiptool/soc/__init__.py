# Copyright (c) Kuba Szczodrzyński 2022-07-29.

from ltchiptool.models import Family

from .interface import SocInterface

__all__ = [
    "SocInterface",
    "get_soc",
]


def get_soc(family: Family) -> SocInterface:
    raise NotImplementedError(f"Unsupported family - {family.name}")

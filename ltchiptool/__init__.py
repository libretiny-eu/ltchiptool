# Copyright (c) Kuba Szczodrzyński 2022-07-29.

from . import util
from .models import Board, Family
from .soc import SocInterface
from .util.env import lt_set_path
from .version import get_version

__all__ = [
    "Board",
    "Family",
    "SocInterface",
    "cli",
    "get_version",
    "lt_set_path",
    "util",
]


def cli():
    from .__main__ import cli

    cli()

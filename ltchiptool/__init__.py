# Copyright (c) Kuba Szczodrzyński 2022-07-29.

from . import util
from .models import Board, Family
from .soc import SocInterface
from .version import get_version

__all__ = [
    "Board",
    "Family",
    "SocInterface",
    "cli",
    "get_version",
    "util",
]


def cli():
    from .__main__ import cli

    cli()

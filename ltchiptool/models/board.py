# Copyright (c) Kuba Szczodrzyński 2022-07-29.

import json
from glob import glob
from os.path import basename, isfile, join
from typing import List, Optional, Tuple, Union

import click

from ltchiptool.util import (
    RecursiveDict,
    Toolchain,
    lt_find_path,
    lt_read_json,
    merge_dicts,
    readjson,
)

from .family import Family


class Board(RecursiveDict):
    _toolchain: Optional[Toolchain] = None

    def __init__(self, board: Union[str, dict]):
        if not isinstance(board, dict):
            if isfile(board):
                board = readjson(board)
            board = lt_read_json(f"boards/{board}.json")
        if "_base" in board:
            base = board["_base"]
            if not isinstance(base, list):
                base = [base]
            result = {}
            for base_name in base:
                board_base = lt_read_json(f"boards/_base/{base_name}.json")
                merge_dicts(result, board_base)
            merge_dicts(result, board)
            board = result
        super(Board, self).__init__(board)

    @classmethod
    def get_list(cls) -> List[str]:
        boards_glob = join(lt_find_path(), "boards", "*.json")
        return [basename(file)[:-5] for file in glob(boards_glob)]

    def json(self) -> str:
        return json.dumps(self, indent=4)

    @property
    def name(self) -> str:
        return self["build.variant"]

    @property
    def title(self) -> str:
        return self["name"]

    @property
    def symbol(self) -> str:
        return self["symbol"]

    @property
    def family(self) -> Family:
        return Family.get(short_name=self["build.family"])

    @property
    def toolchain(self):
        if not self._toolchain:
            self._toolchain = Toolchain(self["build.prefix"])
        return self._toolchain

    def region(self, name: str) -> Tuple[int, int, int]:
        (start, length) = self[f"flash.{name}"].split("+")
        start = int(start, 0)
        length = int(length, 0)
        return start, length, start + length


class BoardParamType(click.ParamType):
    name = "board"

    def convert(self, value, param, ctx) -> Board:
        try:
            return Board(value)
        except FileNotFoundError:
            self.fail(f"Board {value} does not exist", param, ctx)

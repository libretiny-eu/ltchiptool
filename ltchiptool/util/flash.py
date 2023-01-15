#  Copyright (c) Kuba Szczodrzyński 2023-1-15.

from dataclasses import dataclass
from enum import Enum
from typing import IO, Generator, List, Optional

import click
from prettytable import PrettyTable

from .intbin import ByteGenerator


class FlashOp(Enum):
    WRITE = "write"
    READ = "read"
    READ_ROM = "read_rom"


@dataclass
class FlashConnection:
    port: str
    baudrate: Optional[int] = None
    link_baudrate: Optional[int] = None
    timeout: Optional[float] = None
    link_timeout: float = 20.0
    linked: bool = False

    def fill_baudrate(self, baudrate: int) -> None:
        self.link_baudrate = self.link_baudrate or baudrate
        self.baudrate = self.baudrate or self.link_baudrate or baudrate


class ProgressCallback:
    def on_update(self, steps: int) -> None:
        pass

    def on_total(self, total: int) -> None:
        pass

    def on_message(self, message: Optional[str]) -> None:
        pass

    def update_from(self, gen: Generator[int, None, None]) -> None:
        for chunk_len in gen:
            self.on_update(chunk_len)

    def update_with(self, gen: ByteGenerator) -> ByteGenerator:
        while True:
            try:
                chunk = next(gen)
                self.on_update(len(chunk))
                yield chunk
            except StopIteration as e:
                return e.value

    def attach(self, io: IO[bytes]) -> IO[bytes]:
        setattr(io, "_read", io.read)

        def read(n: int = -1) -> bytes:
            data: bytes = getattr(io, "_read")(n)
            self.on_update(len(data))
            return data

        setattr(io, "read", read)
        return io

    @staticmethod
    def detach(io: IO[bytes]) -> IO[bytes]:
        read = getattr(io, "_read", None)
        if read is None:
            return io
        setattr(io, "read", read)
        return io


class ClickProgressCallback(ProgressCallback):
    def __init__(self, length: int = 0, width: int = 64):
        self.bar = click.progressbar(length=length, width=width)

    def on_update(self, steps: int) -> None:
        self.bar.update(steps)

    def on_total(self, total: int) -> None:
        self.bar.length = total
        self.bar.render_progress()

    def on_message(self, message: Optional[str]) -> None:
        self.bar.label = message
        self.bar.render_progress()

    def finish(self) -> None:
        self.bar.render_finish()

    def __enter__(self) -> "ClickProgressCallback":
        self.bar.render_progress()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.bar.render_finish()


def format_flash_guide(soc) -> List[str]:
    guide = []
    dash_line = "-" * 6
    empty_line = " " * 6
    for item in soc.flash_get_guide():
        if isinstance(item, str):
            if guide:
                guide.append(" ")
            guide += item.splitlines()
        elif isinstance(item, list):
            table = PrettyTable()
            left, right = item[0]
            left = left.rjust(6)
            right = right.ljust(6)
            table.field_names = [left, "", right]
            table.align[left] = "r"
            table.align[right] = "l"
            for left, right in item[1:]:
                table.add_row([left, dash_line if left and right else "", right])
            if guide:
                guide.append("")
            for line in table.get_string().splitlines():
                line = line[1:-1]
                line = line.replace(f"-+-{dash_line}-+-", f"-+ {empty_line} +-")
                guide.append(f"    {line}")
    return guide

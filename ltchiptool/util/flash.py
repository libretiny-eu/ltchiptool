#  Copyright (c) Kuba Szczodrzyński 2023-1-15.

from typing import IO, Generator

import click

from .intbin import ByteGenerator


class ProgressCallback:
    def on_update(self, steps: int) -> None:
        pass

    def on_total(self, total: int) -> None:
        pass

    def on_message(self, message: str) -> None:
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

    def on_message(self, message: str) -> None:
        self.bar.label = message
        self.bar.render_progress()

    def finish(self) -> None:
        self.bar.render_finish()

    def __enter__(self) -> "ClickProgressCallback":
        self.bar.render_progress()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.bar.render_finish()

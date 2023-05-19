#  Copyright (c) Kuba Szczodrzyński 2023-1-15.

from abc import ABC
from io import UnsupportedOperation
from typing import IO, Generator, Optional, Type

import click
from hexdump import hexdump

from .intbin import ByteGenerator
from .logging import stream


class StreamHook(ABC):
    def read(self, io: IO[bytes], n: int) -> bytes:
        return getattr(io, "_read")(n)

    def write(self, io: IO[bytes], data: bytes) -> int:
        return getattr(io, "_write")(data)

    def on_after_read(self, data: bytes) -> Optional[bytes]:
        return data

    def on_before_write(self, data: bytes) -> Optional[bytes]:
        return data

    def attach(self, io: IO[bytes], limit: int = 0) -> IO[bytes]:
        if hasattr(io, "_read"):
            return io
        setattr(io, "_read", io.read)
        setattr(io, "_write", io.write)
        try:
            end = io.tell() + limit
        except UnsupportedOperation:
            limit = 0

        def read(n: int = -1) -> bytes:
            if limit > 0:
                # read at most 'limit' bytes
                pos = io.tell()
                n = min(n, end - pos) if limit and n > 0 else n
                if not n:
                    return b""
            data = self.read(io, n)
            data_new = self.on_after_read(data)
            if isinstance(data_new, bytes):
                data = data_new
            return data

        def write(data: bytes) -> int:
            data_new = self.on_before_write(data)
            if isinstance(data_new, bytes):
                data = data_new
            return self.write(io, data)

        setattr(io, "read", read)
        setattr(io, "write", write)
        return io

    @staticmethod
    def detach(io: IO[bytes]) -> IO[bytes]:
        read = getattr(io, "_read", None)
        write = getattr(io, "_read", None)
        if read is not None:
            setattr(io, "read", read)
            delattr(io, "_read")
        if write is not None:
            setattr(io, "write", write)
            delattr(io, "_write")
        return io

    @classmethod
    def register(cls, target: Type, *hook_args, **hook_kwargs) -> None:
        if hasattr(target, "__init_hook__"):
            return
        setattr(target, "__init_hook__", target.__init__)

        # noinspection PyArgumentList
        def init(self, *args, **kwargs):
            self.__init_hook__(*args, **kwargs)
            hook = cls(*hook_args, **hook_kwargs)
            hook.attach(self)

        setattr(target, "__init__", init)

    @staticmethod
    def unregister(target: Type):
        __init__ = getattr(target, "__init_hook__", None)
        if __init__ is not None:
            setattr(target, "__init__", __init__)
            delattr(target, "__init_hook__")

    @classmethod
    def set_registered(cls, target: Type, registered: bool):
        if registered:
            cls.register(target)
        else:
            cls.unregister(target)

    @staticmethod
    def is_registered(target: Type):
        return hasattr(target, "__init_hook__")


class LoggingStreamHook(StreamHook):
    ASCII = bytes(range(32, 128)) + b"\r\n"
    buf: dict

    def __init__(self):
        self.buf = {"-> RX": "", "<- TX": ""}

    def _print(self, data: bytes, msg: str):
        if all(c in self.ASCII for c in data):
            data = data.decode().replace("\r", "")
            while "\n" in data:
                line, _, data = data.partition("\n")
                line = self.buf[msg] + line
                self.buf[msg] = ""
                if line:
                    stream(f"{msg}: '{line}'")
            self.buf[msg] = data
            return

        if self.buf[msg]:
            stream(f"{msg}: '{self.buf[msg]}'")
            self.buf[msg] = ""

        if data.isascii():
            stream(f"{msg}: {data[0:128]}")
        else:
            for line in hexdump(data, "generator"):
                stream(f"{msg}: {line.partition(': ')[2]}")

    def on_after_read(self, data: bytes) -> Optional[bytes]:
        if not data:
            return None
        self._print(data, "-> RX")
        return None

    def on_before_write(self, data: bytes) -> Optional[bytes]:
        self._print(data, "<- TX")
        return None


class ProgressCallback(StreamHook):
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

    def on_after_read(self, data: bytes) -> Optional[bytes]:
        self.on_update(len(data))
        return None


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

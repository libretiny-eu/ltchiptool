#  Copyright (c) Kuba Szczodrzyński 2023-1-15.

from abc import ABC
from io import UnsupportedOperation
from typing import IO, Generator, Optional, Type

import click
from hexdump import hexdump

from .intbin import ByteGenerator
from .logging import stream


class StreamHook(ABC):
    read_key: str
    write_key: str

    def __init__(self) -> None:
        self.read_key = f"_read_{id(self)}"
        self.write_key = f"_write_{id(self)}"

    def read(self, io: IO[bytes], n: int) -> bytes:
        return getattr(io, self.read_key)(n)

    def write(self, io: IO[bytes], data: bytes) -> int:
        return getattr(io, self.write_key)(data)

    def on_after_read(self, data: bytes) -> Optional[bytes]:
        return data

    def on_before_write(self, data: bytes) -> Optional[bytes]:
        return data

    def attach(self, io: IO[bytes], limit: int = 0) -> IO[bytes]:
        if hasattr(io, self.read_key):
            return io
        setattr(io, self.read_key, io.read)
        setattr(io, self.write_key, io.write)
        try:
            end = io.tell() + limit
        except (UnsupportedOperation, AttributeError):
            limit = 0

        def read(n: int = -1) -> bytes:
            if self.is_unregistered(type(io)):
                return getattr(io, self.read_key)(n)
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
            if self.is_unregistered(type(io)):
                return getattr(io, self.write_key)(data)
            data_new = self.on_before_write(data)
            if isinstance(data_new, bytes):
                data = data_new
            return self.write(io, data)

        setattr(io, "read", read)
        setattr(io, "write", write)
        return io

    def detach(self, io: IO[bytes]) -> IO[bytes]:
        read = getattr(io, self.read_key, None)
        write = getattr(io, self.write_key, None)
        if read is not None:
            setattr(io, "read", read)
            delattr(io, self.read_key)
        if write is not None:
            setattr(io, "write", write)
            delattr(io, self.write_key)
        return io

    @classmethod
    def register(cls, target: Type, *hook_args, **hook_kwargs) -> None:
        if hasattr(target, f"__hook_unregistered_{cls.__name__}__"):
            delattr(target, f"__hook_unregistered_{cls.__name__}__")
        if hasattr(target, f"__init_hook_{cls.__name__}__"):
            return
        setattr(target, f"__init_hook_{cls.__name__}__", target.__init__)

        # noinspection PyArgumentList
        def init(self, *args, **kwargs):
            getattr(target, f"__init_hook_{cls.__name__}__")(self, *args, **kwargs)
            hook = cls(*hook_args, **hook_kwargs)
            hook.attach(self)

        setattr(target, "__init__", init)

    @classmethod
    def unregister(cls, target: Type):
        setattr(target, f"__hook_unregistered_{cls.__name__}__", True)
        __init__ = getattr(target, f"__init_hook_{cls.__name__}__", None)
        if __init__ is not None:
            setattr(target, "__init__", __init__)
            delattr(target, f"__init_hook_{cls.__name__}__")

    @classmethod
    def set_registered(cls, target: Type, registered: bool):
        if registered:
            cls.register(target)
        else:
            cls.unregister(target)

    @classmethod
    def is_registered(cls, target: Type):
        return hasattr(target, f"__init_hook_{cls.__name__}__")

    @classmethod
    def is_unregistered(cls, target: Type):
        return hasattr(target, f"__hook_unregistered_{cls.__name__}__")


class LoggingStreamHook(StreamHook):
    ASCII = bytes(range(32, 128)) + b"\r\n"
    buf: dict

    def __init__(self):
        super().__init__()
        self.buf = {"-> RX": "", "<- TX": ""}

    def _print(self, data: bytes, msg: str):
        if data and all(c in self.ASCII for c in data):
            data = data.decode().replace("\r", "")
            while "\n" in data:
                line, _, data = data.partition("\n")
                line = self.buf[msg] + line
                self.buf[msg] = ""
                if line:
                    stream(f"{msg}: '{line}'")
            self.buf[msg] += data
            return

        if self.buf[msg]:
            stream(f"{msg}: '{self.buf[msg]}'")
            self.buf[msg] = ""
        if not data:
            return

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
        self._print(b"", "-> RX")  # print leftover bytes
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
        super().__init__()
        self.bar = click.progressbar(length=length, width=width)

    def on_update(self, steps: int) -> None:
        self.bar.update(steps)

    def on_total(self, total: Optional[int]) -> None:
        self.bar.pos = 0
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

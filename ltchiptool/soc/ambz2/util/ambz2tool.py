#  Copyright (c) Kuba Szczodrzyński 2022-12-21.

import logging
from enum import IntEnum
from hashlib import sha256
from logging import debug, warning
from math import ceil
from time import time
from typing import IO, Callable, Generator, List, Optional

import click
from serial import Serial
from xmodem import XMODEM

from ltchiptool.util.intbin import align_down
from ltchiptool.util.logging import LoggingHandler, verbose
from ltchiptool.util.misc import retry_catching, retry_generator

_T_XmodemCB = Optional[Callable[[int, int, int], None]]


class AmbZ2FlashMode(IntEnum):
    RTL8720CX_CM = 0  # PIN_A7_A12
    RTL8720CF = 1  # PIN_B6_B12


class AmbZ2FlashSpeed(IntEnum):
    SINGLE = 0  # One IO
    DO = 1  # Dual Output
    DIO = 2  # Dual IO
    QO = 3  # Quad Output
    QIO = 4  # Quad IO
    QPI = 5  # QPI


class AmbZ2Tool:
    crc_speed_bps: int = 2000000
    prev_timeout_list: List[float]
    flash_mode: AmbZ2FlashMode = None
    flash_speed: AmbZ2FlashSpeed = AmbZ2FlashSpeed.SINGLE
    flash_hash_offset: int = None

    def __init__(
        self,
        port: str,
        baudrate: int,
        link_timeout: float = 10.0,
        read_timeout: float = 0.6,
        retry_count: int = 10,
    ):
        self.prev_timeout_list = []
        self.link_timeout = link_timeout
        self.read_timeout = read_timeout
        self.retry_count = retry_count

        LoggingHandler.get().attach(logging.getLogger("xmodem.XMODEM"))
        self.s = Serial(port, baudrate)
        self.xm = XMODEM(
            getc=lambda size, timeout=1: self.read(size) or None,
            putc=lambda data, timeout=1: self.write(data),
            mode="xmodem1k",
        )

    @property
    def flash_cfg(self) -> str:
        return f"{self.flash_speed} {self.flash_mode}"

    #################################
    # Serial transmission utilities #
    #################################

    def close(self) -> None:
        self.s.close()
        self.s = None

    def write(self, data: bytes) -> None:
        self.s.write(data)

    def command(self, cmd: str) -> None:
        self.flush()
        self.s.write(cmd.encode() + b"\n")

    def read(self, count: int = None) -> bytes:
        response = b""
        end = time() + self.read_timeout
        end_nb = time() + 0.01  # not before
        while time() < end:
            read = self.s.read_all()
            response += read
            if count and len(response) >= count:
                break
            if not response or time() <= end_nb:
                continue
            if not read:
                break

        if not response:
            raise TimeoutError(f"Timeout in read({count}) - no data received")
        if not count:
            return response
        response = response[:count]
        if len(response) != count:
            raise TimeoutError(f"Timeout in read({count}) - not enough data received")
        return response

    def readlines(self) -> Generator[str, None, None]:
        response = b""
        end = time() + self.read_timeout
        self.s.timeout = self.read_timeout
        while time() < end:
            read = self.s.read_all()
            if not read:
                continue
            end = time() + self.read_timeout
            while b"\n" in read:
                line, _, read = read.partition(b"\n")
                line = (response + line).decode().strip()
                if not line:
                    continue
                yield line
                response = b""
            response += read
        raise TimeoutError("Timeout in readlines() - no more data received")

    def flush(self) -> None:
        self.s.read_all()
        self.s.flush()

    def push_timeout(self, timeout: float) -> None:
        verbose(f"push_timeout({timeout})")
        self.prev_timeout_list.append(self.read_timeout)
        self.read_timeout = timeout

    def pop_timeout(self) -> None:
        verbose("pop_timeout()")
        self.read_timeout = self.prev_timeout_list.pop(-1)

    def error_flush(self) -> None:
        # try to clean up the serial buffer
        # no data for 0.8 s means that the chip stopped sending bytes
        self.push_timeout(0.8)
        while True:
            if not self.s.read(128):
                break
        self.pop_timeout()
        # pop timeout of the failing function
        self.pop_timeout()

    #########################################
    # Basic commands - public low-level API #
    #########################################

    def ping(self) -> None:
        self.command("ping")
        resp = self.read(4)
        if resp != b"ping":
            raise RuntimeError(f"incorrect ping response: {resp!r}")

    def disconnect(self) -> None:
        self.command("disc")

    def link(self) -> None:
        end = time() + self.link_timeout
        while time() < end:
            try:
                self.ping()
                return
            except (RuntimeError, TimeoutError):
                pass
        raise TimeoutError("Timeout while linking")

    def change_baudrate(self, baudrate: int) -> None:
        if self.s.baudrate == baudrate:
            return
        self.ping()
        self.command(f"ucfg {baudrate} 0 0")
        # change Serial port baudrate
        debug("-- UART: Changing port baudrate")
        self.s.baudrate = baudrate
        # wait up to 1 second for OK response
        self.push_timeout(1.0)
        resp = self.read()
        if resp != b"OK":
            raise RuntimeError(f"baud rate change not OK: {resp!r}")

        self.pop_timeout()
        # link again to make sure it still works
        self.link()

    def dump_words(self, start: int, count: int) -> Generator[List[int], None, None]:
        # at most ~350ms for initial output, when reading at least 256 words
        self.push_timeout(max(min(count, 256), 16) * 1.5 / 500.0)
        try:
            # one line is 57 chars long, and it holds 4 words
            # make it 32 KiB at most
            self.s.set_buffer_size(rx_size=min(32768, 57 * (count // 4)))
        except AttributeError:
            # Serial.set_buffer_size is only available on win32
            pass

        read_count = 0
        self.flush()
        self.command(f"DW {start:X} {count}")
        count *= 4

        for line in self.readlines():
            line = line.split()
            addr = int(line[0].rstrip(":"), 16)
            if addr != start + read_count:
                raise ValueError("Got invalid read address")

            chunk = list()
            for i, value in enumerate(line[1 : 1 + 4]):
                value = int(value, 16)
                chunk.append(value)
                read_count += 4
                if read_count >= count:
                    break
            yield chunk
            if read_count >= count:
                break
        self.pop_timeout()

    def dump_bytes(self, start: int, count: int) -> Generator[bytes, None, None]:
        # at most ~350ms for initial output, when reading at least 1024 bytes
        self.push_timeout(max(min(count, 1024), 64) * 0.5 / 500.0)
        try:
            # one line is 78 chars long, and it holds 16 bytes
            # make it 32 KiB at most
            self.s.set_buffer_size(rx_size=min(32768, 78 * (count // 16)))
        except AttributeError:
            # Serial.set_buffer_size is only available on win32
            pass

        read_count = 0
        self.flush()
        self.command(f"DB {start:X} {count}")

        for line in self.readlines():
            line = line.split()
            if line[0] == "[Addr]":
                continue
            addr = int(line[0].rstrip(":"), 16)
            if addr != start + read_count:
                raise ValueError("Got invalid read address")

            chunk = bytearray()
            if len(line) < 17:
                raise ValueError(f"Not enough data in line {line}")
            for i, value in enumerate(line[1 : 1 + 16]):
                value = int(value, 16)
                chunk.append(value)
                read_count += 1
                if read_count >= count:
                    break
            yield chunk
            if read_count >= count:
                break
        self.pop_timeout()

    def register_read(self, address: int) -> int:
        start = align_down(address, 4)
        regs = list(self.dump_words(start=start, count=4))
        return regs[0][address - start]

    def register_write(self, address: int, value: int) -> None:
        self.command(f"EW {address:X} {value:X}")
        next(self.readlines())

    def sw_reset(self) -> None:
        self.command("WDTRST")

    ###############################################
    # Flash-related commands - for internal usage #
    ###############################################

    def flash_init(self, configure: bool = True) -> None:
        if self.flash_mode is None:
            reg = self.register_read(0x4000_0038)
            self.flash_mode = AmbZ2FlashMode((reg >> 5) & 0b11)
            self.register_write(0x4000_2800, 0x7EFF_FFFF)
            debug(f"Flash mode read: {self.flash_mode}")
        if self.flash_hash_offset is None and configure:
            self.flash_read_hash(offset=None, length=0)
            debug(
                f"Flash set up: "
                f"mode={self.flash_mode.name}, "
                f"speed={self.flash_speed.name}"
            )

    def flash_read_hash(self, offset: Optional[int], length: int) -> bytes:
        # set the flash_mode
        self.flash_init(configure=False)

        # configure start offset of "hashq"
        if self.flash_hash_offset != offset:
            retry_catching(
                retries=self.retry_count,
                doc="Hash offset set error",
                func=self.flash_transmit,
                onerror=self.error_flush,
                stream=None,
                offset=offset,
            )

        timeout = self.read_timeout
        timeout_minimum = ceil(length / self.crc_speed_bps * 10.0) / 10.0
        if timeout_minimum > timeout:
            warning(
                "WARN: The current command timeout of "
                f"{timeout} "
                "second(s) is too low for reading "
                f"{length} "
                "bytes hash. Increasing to "
                f"{timeout_minimum} "
                "second(s).",
            )
            timeout = timeout_minimum

        # read SHA256 hash
        cmd = f"hashq {length} {self.flash_cfg}"
        self.command(cmd)
        # wait for response
        self.push_timeout(timeout)
        response = self.read(count=6 + 32)
        self.pop_timeout()

        if not response.startswith(b"hashs "):
            raise RuntimeError(f"Unexpected response to '{cmd}': {response}")
        return response[6 : 6 + 32]

    def flash_transmit(
        self,
        stream: Optional[IO[bytes]],
        offset: int,
        callback: _T_XmodemCB = None,
    ) -> None:
        # set the flash_mode
        self.flash_init(configure=False)

        # increase timeout to read XMODEM bytes (RTL processes requests every ~1.0s)
        self.push_timeout(3.0)

        self.command(f"fwd {self.flash_cfg} {offset:x}")
        self.flash_hash_offset = offset

        if not stream:
            debug("XMODEM: starting empty transmission")
            # wait for NAK
            resp = self.read(1)
            if resp != b"\x15":
                raise RuntimeError(f"expected NAK, got {resp!r}")

            # abort using CAN
            self.xm.abort()
            self.flush()
            # wait for CAN response
            resp = self.read(3)
            if resp != b"\x18ER":
                raise RuntimeError(f"expected CAN, got {resp!r}")
        else:
            debug(f"XMODEM: transmitting to 0x{offset:X}")
            if not self.xm.send(stream, callback=callback):
                raise RuntimeError("XMODEM transmission failed")

        self.pop_timeout()
        self.link()

    def ram_transmit(
        self,
        stream: IO[bytes],
        offset: int,
        callback: _T_XmodemCB = None,
    ) -> None:
        # increase timeout to read XMODEM bytes (RTL processes requests every ~1.0s)
        self.push_timeout(2.0)

        self.command(f"fwdram {offset:x}")

        debug(f"XMODEM: transmitting to 0x{offset:X}")
        if not self.xm.send(stream, callback=callback):
            raise RuntimeError("XMODEM transmission failed")

        self.pop_timeout()
        self.link()

    #######################################
    # Memory-related commands - public API #
    #######################################

    def memory_read(
        self,
        offset: int,
        length: int,
        use_flash: bool,
        hash_check: bool = True,
        hash_incremental: bool = True,
        chunk_size: int = 32 * 1024,
        yield_size: int = 32 * 1024,
        hash_check_size: int = 128 * 1024,
    ) -> Generator[bytes, None, None]:
        if use_flash:
            # set the flash_mode & initialize it
            self.flash_init()
        else:
            # can only check SHA of flash
            hash_check = False

        chunk = b""
        sha = sha256()
        sha_size = 0
        read_count = 0
        # can't check hash mid-chunk, as the RTL is still sending data
        if hash_check_size < chunk_size:
            hash_check_size = chunk_size
        for start in range(offset, offset + length, chunk_size):
            count = min(start + chunk_size, offset + length) - start
            if use_flash:
                start |= 0x9800_0000
            debug(f"Dumping bytes: start=0x{start:X}, count=0x{count:X}")

            def dump():
                nonlocal chunk, read_count, sha_size, read_count, start, count
                verbose(f"dump_bytes(0x{start:X}, {count})")
                for data in self.dump_bytes(start, count):
                    chunk += data
                    read_count += len(data)
                    if hash_check:
                        sha.update(data)
                        sha_size += len(data)
                    # increment offset and length for subsequent error retries
                    start += len(data)
                    count -= len(data)
                    # yield the block every 'yield_size' bytes
                    if len(chunk) >= yield_size or read_count >= length:
                        yield chunk
                        chunk = b""

            yield from retry_generator(
                retries=self.retry_count,
                doc="Data read error",
                func=dump,
                onerror=self.error_flush,
            )

            # check SHA256 incrementally every 'hash_check_size' bytes
            check_block_hash = hash_incremental and sha_size >= hash_check_size
            check_final_hash = read_count >= length
            if hash_check and (check_block_hash or check_final_hash):
                debug(
                    ("Incremental " if hash_incremental else "Final ") + f"hash check: "
                    f"start=0x{offset:X}, "
                    f"count=0x{read_count:X}",
                )
                hash_final = sha.digest()
                hash_expected = retry_catching(
                    retries=self.retry_count,
                    doc="Hash check error",
                    func=self.flash_read_hash,
                    onerror=self.error_flush,
                    offset=offset,
                    length=read_count,
                )
                if hash_final != hash_expected:
                    raise ValueError(
                        f"Chip SHA256 value does not match calculated "
                        f"value (at 0x{offset:X}+0x{read_count:X}). Expected: "
                        f"{hash_expected.hex()}, calculated: {hash_final.hex()}"
                    )
                sha_size = 0

    def memory_write(
        self,
        offset: int,
        stream: IO[bytes],
        use_flash: bool,
        hash_check: bool = True,
        chunk_size: int = 32 * 1024,
        callback: _T_XmodemCB = None,
    ) -> None:
        if not use_flash:
            # can only check SHA of flash
            hash_check = False

        base = stream.tell()

        if use_flash:
            self.flash_transmit(stream, offset, callback=callback)
        else:
            self.ram_transmit(stream, offset, callback=callback)

        if hash_check:
            length = stream.tell() - base
            # rewind stream
            stream.seek(base)
            # on py >= 3.11 use:
            # sha = hashlib.file_digest(stream, sha256)
            sha = sha256(stream.read(length))
            hash_expected = sha.digest()

            debug(f"hash check: start={offset:#X}, count={length:#X}")
            hash_final = self.flash_read_hash(offset, length)
            if hash_final != hash_expected:
                raise ValueError(
                    f"Chip SHA256 value does not match calculated "
                    f"value (at 0x{offset:X}). Expected: "
                    f"{hash_expected.hex()}, calculated: {hash_final.hex()}"
                )


@click.command(
    help="AmebaZ2 flashing tool",
)
def cli():
    raise NotImplementedError()


if __name__ == "__main__":
    cli()

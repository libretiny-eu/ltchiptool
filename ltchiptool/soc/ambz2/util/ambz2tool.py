#  Copyright (c) Kuba Szczodrzyński 2022-12-21.

import logging
from enum import IntEnum
from hashlib import sha256
from logging import debug, warning
from math import ceil
from time import time
from typing import IO, Callable, Generator, List, Optional, Tuple

import click
from hexdump import hexdump, restore
from serial import Serial
from xmodem import XMODEM

from ltchiptool.util.cli import DevicePortParamType
from ltchiptool.util.intbin import align_down, biniter, gen2bytes, letoint, pad_data
from ltchiptool.util.logging import LoggingHandler, verbose
from ltchiptool.util.misc import retry_catching, retry_generator
from ltchiptool.util.serialtool import SerialToolBase

_T_XmodemCB = Optional[Callable[[int, int, int], None]]

AMBZ2_FALLBACK_CMD = b"Rtk8710C\n"
AMBZ2_FALLBACK_RESP = [
    b"\r\n$8710c>" * 2,
    b"Rtk8710C\r\nCommand NOT found.\r\n$8710c>",
]
USED_COMMANDS = [
    "ping",
    "disc",
    "ucfg",
    "DW",
    "DB",
    "EW",
    "EB",
    "WDTRST",
    "hashq",
    "fwd",
    "fwdram",
]

AMBZ2_CODE_ADDR = 0x10037000
AMBZ2_DATA_ADDR = 0x10038000
AMBZ2_EFUSE_PHYSICAL_SIZE = 512
AMBZ2_EFUSE_LOGICAL_SIZE = 512

AMBZ2_CHIP_TYPE = {
    0xFE: "RTL87x0CF",
}


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


class AmbZ2Tool(SerialToolBase):
    crc_speed_bps: int = 1500000
    flash_mode: AmbZ2FlashMode = None
    flash_speed: AmbZ2FlashSpeed = AmbZ2FlashSpeed.SINGLE
    flash_hash_offset: int = None
    in_fallback_mode: bool = False
    boot_cmd: Tuple[int, str] = None

    def __init__(
        self,
        port: str,
        baudrate: int,
        link_timeout: float = 10.0,
        read_timeout: float = 0.6,
        retry_count: int = 10,
    ):
        super().__init__(port, baudrate, link_timeout, read_timeout, retry_count)
        LoggingHandler.get().attach(logging.getLogger("xmodem.XMODEM"))
        self.xm = XMODEM(
            getc=lambda size, timeout=1: self.read(size) or None,
            putc=lambda data, timeout=1: self.write(data),
            mode="xmodem1k",
        )

    @property
    def flash_cfg(self) -> str:
        return f"{self.flash_speed} {self.flash_mode}"

    #########################################
    # Basic commands - public low-level API #
    #########################################

    def command(self, cmd: str) -> None:
        self.flush()
        cmd = cmd.encode()
        self.s.write(cmd + b"\n")
        if self.in_fallback_mode:
            self.s.read(len(cmd) + 2)

    def ping(self) -> None:
        self.command("ping")
        resp = self.read(4)
        if resp != b"ping":
            raise RuntimeError(f"Incorrect ping response: {resp!r}")
        resp = self.s.read_all()
        if b"$8710c" in resp:
            raise RuntimeError(f"Got fallback mode ping: {resp!r}")

    def disconnect(self) -> None:
        self.command("disc")

    def link(self) -> None:
        # try linking in fallback mode - 'ping' before that would break it
        self.link_fallback()
        end = time() + self.link_timeout
        while time() < end:
            try:
                self.ping()
                return
            except (RuntimeError, TimeoutError):
                pass
        raise TimeoutError("Timeout while linking")

    def link_fallback(self) -> None:
        self.flush()
        self.write(AMBZ2_FALLBACK_CMD)
        self.push_timeout(0.1)
        try:
            response = self.read()
            if response not in AMBZ2_FALLBACK_RESP:
                return
        except TimeoutError:
            return
        finally:
            self.pop_timeout()
        debug(f"Found fallback mode with response: {response}")
        self.in_fallback_mode = True
        # check ROM version
        chip_ver = (self.register_read(0x4000_01F0) >> 4) & 0xF
        # jump to download mode
        self.memory_boot(0x0 if chip_ver > 2 else 0x1443C)
        self.in_fallback_mode = False

    def change_baudrate(self, baudrate: int) -> None:
        if self.s.baudrate == baudrate:
            return
        self.ping()
        self.command(f"ucfg {baudrate} 0 0")
        # change Serial port baudrate
        self.set_baudrate(baudrate)
        # wait up to 1 second for OK response
        self.push_timeout(1.0)
        try:
            resp = self.read()
        except TimeoutError:
            raise RuntimeError("Timed out while changing baud rate")
        if resp != b"OK":
            raise RuntimeError(f"Baud rate change not OK: {resp!r}")

        self.pop_timeout()
        # link again to make sure it still works
        self.link()

    def dump_words(self, start: int, count: int) -> Generator[List[int], None, None]:
        # at most ~350ms for initial output, when reading at least 256 words
        self.push_timeout(max(min(count, 256), 16) * 1.5 / 500.0)
        # one line is 57 chars long, and it holds 4 words
        # make it 32 KiB at most
        try:
            self.s.set_buffer_size(rx_size=min(32768, 57 * (count // 4)))
        except AttributeError:
            pass

        read_count = 0
        self.flush()
        self.command(f"DW {start:X} {count}")
        count *= 4

        for line in self.readlines():
            line = line.split()
            addr = int(line[0].rstrip(":"), 16)
            if addr != start + read_count:
                raise ValueError(f"Got invalid read address: {line}")

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
        # one line is 78 chars long, and it holds 16 bytes
        # make it 32 KiB at most
        try:
            self.s.set_buffer_size(rx_size=min(32768, 78 * (count // 16)))
        except AttributeError:
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

    def register_read_bytes(self, address: int, length: int) -> bytes:
        start = align_down(address, 4)
        return gen2bytes(self.dump_bytes(start, length))[0:length]

    def register_write_bytes(self, address: int, value: bytes) -> None:
        start = align_down(address, 4)
        value = pad_data(value, 4, 0x00)
        words = []
        for word in biniter(value, 4):
            words.append(f"{letoint(word):X}")
        # 'EW' command can theoretically write at most 8 words,
        # but it seems to cut the command off at around 80 bytes
        for i in range(0, len(words), 7):
            chunk = words[i : i + 7]
            command = f"EW {start + i * 4:X} "
            command += " ".join(chunk)
            self.command(command)
            lines = self.readlines()
            for _ in chunk:
                next(lines)

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

        # determine a reliable maximum chunk size
        baud_coef = int(1 / self.s.baudrate**0.5 * 2000)
        chunk_size = min(2**baud_coef * 1024, chunk_size)

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

    def memory_boot(
        self,
        address: int,
        force_find: bool = False,
    ) -> None:
        address |= 1
        if self.boot_cmd is None or force_find:
            # find ROM console command array
            cmd_array = self.register_read(0x1002F050 + 4)
            cmd_size = 4 * 3
            # try all commands to find an unused one
            for cmd_ptr in range(cmd_array, cmd_array + 8 * cmd_size, cmd_size):
                # read command name pointer
                name_ptr = self.register_read(cmd_ptr + 0)
                if name_ptr == 0:
                    break
                # read command name
                cmd_name = b"".join(self.dump_bytes(name_ptr, 16))
                cmd_name = cmd_name.partition(b"\x00")[0]
                if not cmd_name.isascii():
                    warning(f"Non-ASCII command string @ 0x{name_ptr:X}: {cmd_name}")
                    continue
                cmd_name = cmd_name.decode()
                if cmd_name in USED_COMMANDS:
                    continue
                func_ptr = cmd_ptr + 4
                self.boot_cmd = func_ptr, cmd_name
        if self.boot_cmd is None:
            raise RuntimeError("No unused ROM command found, cannot boot from SRAM")

        func_ptr, cmd_name = self.boot_cmd
        # write new command handler address
        self.register_write(func_ptr, address)
        debug(f"Jumping to 0x{address:X} with command '{cmd_name}'")
        # execute command to jump to the function
        self.command(cmd_name)


@click.command(
    help="AmebaZ2 flashing tool",
)
@click.option(
    "-d",
    "--device",
    help="Target device port (default: auto detect)",
    type=DevicePortParamType(),
    default=(),
)
def cli(device: str):
    s = Serial(device, 115200)
    s.timeout = 0.01

    while True:
        cmd = input("> ")

        if cmd == "m":
            try:
                while True:
                    read = s.read_all()
                    if read:
                        print(read.decode(errors="replace"), end="")
            except KeyboardInterrupt:
                continue

        s.write(cmd.encode())
        s.write(b"\r\n")
        response = b""
        start = time()

        if cmd.startswith("ucfg"):
            s.close()
            baud = int(cmd.split(" ")[1])
            s = Serial(device, baud)

        if cmd.startswith("DB"):
            f = open(cmd + ".bin", "wb")
            while True:
                try:
                    read = s.read_all()
                    if read:
                        print(read.decode(), end="")
                        response += read
                    while b"\n" in response:
                        line, _, response = response.partition(b"\n")
                        line = line.decode()
                        line = line.strip()
                        if line and "[Addr]" not in line:
                            f.write(restore(line))
                except KeyboardInterrupt:
                    break
            f.close()
            continue

        while True:
            response += s.read_all()
            if time() > start + 0.5:
                break
        hexdump(response)


if __name__ == "__main__":
    cli()

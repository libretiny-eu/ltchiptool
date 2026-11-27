#  Copyright (c) 2026 bavci1988.

"""
Serial flasher for the XRadio XR806 boot ROM ("BROM" protocol).

The protocol was worked out from the PhoenixMC tool that ships with the XR806 SDK.

Every command is a frame of a 12-byte header and a payload:

    0   4  magic "BROM"
    4   1  flags (bit 2: frame has a checksum)
    5   1  reserved (in a reply: BROM version)
    6   2  checksum, big-endian
    8   4  payload length, big-endian
    12  -  payload: command byte, then its arguments (big-endian)

The checksum is the inverted 16-bit little-endian word sum of the header and the
payload. It is calculated while the multi-byte fields (checksum, length and the
command arguments) still hold their little-endian values, and those fields are
byte-swapped to big-endian afterwards.

A reply has the same header. Flag bit 0 means an error, and one byte with the error
code follows. Flag bit 1 means "acknowledged", and the payload follows. Flag bit 2
means the reply has a checksum: the word sum over the reply, including its
checksum, must then be 0xFFFF.

Commands that send data (write memory, write sectors) are acknowledged twice:
once for the command frame, and once after the data was sent raw.
"""

import struct
from logging import debug, info, warning
from time import sleep, time
from typing import IO, Callable, Generator, List, Optional, Tuple

import click

from ltchiptool.util.cli import DevicePortParamType
from ltchiptool.util.serialtool import SerialToolBase

XR806_ROM_BAUDRATE = 115200
XR806_MAX_BAUDRATE = 921600
XR806_SECTOR_SIZE = 512
XR806_BLOCK_SIZE = 0x10000
XR806_WRITE_CHUNK = 0x4000
# Boot ROM versions 1 and older need PhoenixMC's proprietary RAM flash helper, which is not included
XR806_MIN_BROM_VERSION = 2
# the boot ROM ends below 0x28000 (rom_symbol.ld of the SDK)
XR806_ROM_SIZE = 0x28000
# the eFuse controller mirrors the 1024 eFuse bits in its VALUE registers (hal_efuse.h of the SDK)
XR806_EFUSE_ADDRESS = 0x40043D00
XR806_EFUSE_SIZE = 128

FRAME_MAGIC = b"BROM"
FLAG_ERROR = 0x01
FLAG_ACK = 0x02
FLAG_CHECKSUM = 0x04

CMD_READ_MEMORY = 0x08
CMD_WRITE_MEMORY = 0x09
CMD_CHANGE_BAUD = 0x10
CMD_REBOOT = 0x12
CMD_SET_PC = 0x13
CMD_GET_FLASH_ID = 0x18
CMD_ERASE = 0x19
CMD_READ_SECTORS = 0x1A
CMD_WRITE_SECTORS = 0x1B

ERASE_BLOCK_64K = 0x03
# PhoenixMC sends the baud rate with this in its top byte
BAUD_CONFIG = 0x03000000

ERRORS = {
    1: "Unknown command",
    2: "Command timeout",
    3: "Checksum error",
    4: "Invalid command",
    5: "Out of memory",
}

_T_ProgressCB = Optional[Callable[[int], None]]


class UnsupportedBootRomError(Exception):
    """The chip answered, but its boot ROM cannot be used without PhoenixMC's flash helper."""


def sum16(data: bytes) -> int:
    """16-bit sum of little-endian words; an odd last byte is added as is."""
    total = sum(struct.unpack_from(f"<{len(data) // 2}H", data))
    if len(data) % 2:
        total += data[-1]
    return total & 0xFFFF


def checksum16(data: bytes) -> int:
    return ~sum16(data) & 0xFFFF


def build_frame(cmd: int, args: List[Tuple[str, int]]) -> bytes:
    """Build a command frame. 'args' are (struct format, value) pairs."""
    payload_le = bytes([cmd]) + b"".join(struct.pack("<" + f, v) for f, v in args)
    payload_be = bytes([cmd]) + b"".join(struct.pack(">" + f, v) for f, v in args)
    header = FRAME_MAGIC + bytes([FLAG_CHECKSUM, 0])
    length = len(payload_le)
    chk = checksum16(header + b"\x00\x00" + struct.pack("<I", length) + payload_le)
    return header + struct.pack(">HI", chk, length) + payload_be


class XR806Tool(SerialToolBase):
    brom_version: Optional[int] = None
    flash_id: Optional[bytes] = None

    def __init__(
        self,
        port: str,
        baudrate: int,
        link_timeout: float = 20.0,
        read_timeout: float = 1.0,
        retry_count: int = 10,
    ):
        super().__init__(port, baudrate, link_timeout, read_timeout, retry_count)

    #########################################
    # Frame transport                       #
    #########################################

    def _read_reply(self) -> Tuple[int, bytes]:
        header = self.read(12)
        if header[0:4] != FRAME_MAGIC:
            self.timed_flush()
            raise ValueError(f"Invalid reply header: {header.hex()}")
        flags = header[4]
        if flags & FLAG_ERROR:
            code = self.read(1)[0]
            raise RuntimeError(f"Command failed: {ERRORS.get(code, f'error {code}')}")
        if not flags & FLAG_ACK:
            raise ValueError(f"Reply without ACK flag: {header.hex()}")
        chk, length = struct.unpack(">HI", header[6:12])
        payload = self.read(length) if length else b""
        if flags & FLAG_CHECKSUM:
            # the sum is taken with the checksum and length as little-endian values
            raw = header[0:6] + struct.pack("<HI", chk, length) + payload
            if sum16(raw) != 0xFFFF:
                raise ValueError("Reply checksum error")
        return header[5], payload

    def command(
        self,
        cmd: int,
        args: List[Tuple[str, int]] = None,
        data: bytes = None,
        timeout: float = None,
    ) -> bytes:
        frame = build_frame(cmd, args or [])
        debug(f"<- TX: {frame.hex(' ')}")
        self.flush()
        self.push_timeout(timeout or self.read_timeout)
        try:
            self.write(frame)
            version, payload = self._read_reply()
            if data is not None:
                self.write(data)
                version, payload = self._read_reply()
        finally:
            self.pop_timeout()
        debug(f"-> RX: {payload[:32].hex(' ')}")
        self.brom_version = version
        return payload

    #########################################
    # Basic commands - public low-level API #
    #########################################

    def send_upgrade(self) -> None:
        """Ask a running SDK application to reboot into the boot ROM."""
        self.write(b"upgrade\n\x00")
        sleep(0.05)

    def sync(self, timeout: float = None) -> None:
        end = time() + (timeout or self.link_timeout)
        self.push_timeout(0.05)
        try:
            while time() < end:
                self.write(b"\x55")
                try:
                    if self.read(2) == b"OK":
                        return
                except TimeoutError:
                    pass
        finally:
            self.pop_timeout()
        raise TimeoutError("Timeout while syncing with the boot ROM")

    def link(self) -> None:
        self.send_upgrade()
        self.sync()
        self.get_flash_id()

    def get_flash_id(self) -> bytes:
        self.flash_id = self.command(CMD_GET_FLASH_ID)
        debug(f"BROM version {self.brom_version}, flash ID {self.flash_id.hex()}")
        return self.flash_id

    def get_flash_size(self) -> Optional[int]:
        """Flash size from the JEDEC capacity byte, if it looks valid."""
        fid = self.flash_id or self.get_flash_id()
        for capacity in fid[2:3] + fid[0:1]:
            if 0x10 <= capacity <= 0x19:
                return 1 << capacity
        return None

    def change_baudrate(self, baudrate: int) -> None:
        if self.s.baudrate == baudrate:
            return
        self.command(CMD_CHANGE_BAUD, [("I", baudrate | BAUD_CONFIG)])
        self.set_baudrate(baudrate)
        sleep(0.01)
        self.sync(timeout=2.0)

    def read_memory(self, address: int, length: int) -> bytes:
        data = self.command(CMD_READ_MEMORY, [("I", address), ("I", length)])
        if len(data) != length:
            raise ValueError(f"Read {len(data)} bytes, expected {length}")
        return data

    def write_memory(self, address: int, data: bytes) -> None:
        self.command(
            CMD_WRITE_MEMORY,
            [("I", address), ("I", len(data)), ("H", checksum16(data))],
            data=data,
            timeout=3.0,
        )

    def set_pc(self, address: int) -> None:
        self.command(CMD_SET_PC, [("I", address)])

    def reboot(self) -> None:
        try:
            self.command(CMD_REBOOT, timeout=0.5)
        except (TimeoutError, ValueError):
            pass

    def erase_block(self, address: int) -> None:
        self.command(
            CMD_ERASE,
            [("B", ERASE_BLOCK_64K), ("I", address)],
            timeout=5.0,
        )

    def read_sectors(self, sector: int, count: int) -> bytes:
        data = self.command(CMD_READ_SECTORS, [("I", sector), ("I", count)])
        if len(data) != count * XR806_SECTOR_SIZE:
            raise ValueError(f"Read {len(data)} bytes, expected {count * 512}")
        return data

    def write_sectors(self, sector: int, data: bytes) -> None:
        if len(data) % XR806_SECTOR_SIZE:
            raise ValueError("Data must be a multiple of the sector size")
        count = len(data) // XR806_SECTOR_SIZE
        self.command(
            CMD_WRITE_SECTORS,
            [("I", sector), ("I", count), ("H", checksum16(data))],
            data=data,
            timeout=5.0,
        )

    #########################################
    # Flash helpers - public high-level API #
    #########################################

    def prepare(self, baudrate: int) -> None:
        """Link, check the boot ROM version, and switch to 'baudrate'."""
        self.link()
        if (self.brom_version or 0) < XR806_MIN_BROM_VERSION:
            raise UnsupportedBootRomError(
                f"Boot ROM version {self.brom_version} is not supported "
                f"(it needs PhoenixMC's flash helper); use PhoenixMC for this chip"
            )
        self.change_baudrate(baudrate)

    def flash_read(
        self,
        offset: int,
        length: int,
        callback: _T_ProgressCB = None,
    ) -> Generator[bytes, None, None]:
        # PhoenixMC reads 2 KiB per command at 921600 baud and 512 bytes below that
        chunk = 0x800 if self.s.baudrate >= XR806_MAX_BAUDRATE else 0x200
        start = offset - offset % XR806_SECTOR_SIZE
        end = offset + length
        addr = start
        while addr < end:
            size = min(chunk, end - addr)
            count = -(-size // XR806_SECTOR_SIZE)
            data = self.read_sectors(addr // XR806_SECTOR_SIZE, count)
            lo = max(offset - addr, 0)
            hi = min(end - addr, len(data))
            part = data[lo:hi]
            if callback:
                callback(len(part))
            yield part
            addr += count * XR806_SECTOR_SIZE

    def memory_read(
        self,
        address: int,
        length: int,
        callback: _T_ProgressCB = None,
    ) -> Generator[bytes, None, None]:
        chunk = 0x800 if self.s.baudrate >= XR806_MAX_BAUDRATE else 0x200
        end = address + length
        while address < end:
            data = self.read_memory(address, min(chunk, end - address))
            if callback:
                callback(len(data))
            yield data
            address += len(data)

    def flash_write(
        self,
        offset: int,
        stream: IO[bytes],
        length: int,
        callback: _T_ProgressCB = None,
    ) -> None:
        """
        Write 'length' bytes at 'offset'. The flash is erased in 64 KiB blocks, so
        the data of a block that is outside the written range is read first and
        written back. Chunks that are fully erased (0xFF) are not sent.
        """
        end = offset + length
        block = offset - offset % XR806_BLOCK_SIZE
        while block < end:
            block_end = block + XR806_BLOCK_SIZE
            lo = max(offset, block)
            hi = min(end, block_end)
            data = stream.read(hi - lo)
            if len(data) != hi - lo:
                raise ValueError("Not enough data in the input stream")
            head = b"".join(self.flash_read(block, lo - block)) if lo > block else b""
            tail = (
                b"".join(self.flash_read(hi, block_end - hi)) if hi < block_end else b""
            )
            buf = head + data + tail
            self.erase_block(block)
            for pos in range(0, XR806_BLOCK_SIZE, XR806_WRITE_CHUNK):
                part = buf[pos : pos + XR806_WRITE_CHUNK]
                if part.count(0xFF) == len(part):
                    continue
                self.write_sectors((block + pos) // XR806_SECTOR_SIZE, part)
            if callback:
                callback(hi - lo)
            block = block_end


@click.command(
    help="XR806 flashing tool",
)
@click.option(
    "-d",
    "--device",
    help="Target device port (default: auto detect)",
    type=DevicePortParamType(),
    default=(),
)
@click.option(
    "-b",
    "--baudrate",
    help="Baud rate for flash access (default: 921600)",
    type=int,
    default=XR806_MAX_BAUDRATE,
)
def cli(device: str, baudrate: int):
    xr806 = XR806Tool(port=device, baudrate=XR806_ROM_BAUDRATE)
    info("Linking... (hold PB02 low and reset the chip)")
    xr806.prepare(baudrate)
    info(f"BROM version: {xr806.brom_version}")
    info(f"Flash ID: {xr806.flash_id.hex(' ').upper()}")
    size = xr806.get_flash_size()
    if size:
        info(f"Flash size: {size // 1024} KiB")
    else:
        warning("Flash size not recognized")
    xr806.change_baudrate(XR806_ROM_BAUDRATE)
    xr806.close()


if __name__ == "__main__":
    cli()

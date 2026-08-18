# Copyright (c) Bl00d-B0b 2026-08-07.

"""AmebaD (RTL8720D) UART download tool.

Same ROM command set as AmebaZ (single-byte commands, ACK 0x06). Flash access
needs the RAM flashloader first (KM0 SRAM at 0x82000, 115200 baud). Loader
READ (0x20, offset + 4 KB sector count) streams XMODEM-1K with 8-bit checksums,
ACK-paced, without an initiation byte; WRITE is erase + XMODEM through the XIP
window, after which the loader falls back to 115200; CMD_CRC (32-bit LE dword
sum) verifies both. Outgoing XMODEM payloads carry a 4-byte LE destination
address; received packets are plain XMODEM-1K.
"""

import logging
import struct
from io import BytesIO
from logging import debug, info
from time import sleep
from typing import IO, Callable, Generator, Optional

from xmodem import XMODEM

from ltchiptool.util.intbin import align_down, align_up, inttole16, inttole24, letoint
from ltchiptool.util.logging import LoggingHandler, verbose
from ltchiptool.util.misc import retry_generator
from ltchiptool.util.serialtool import SerialToolBase
from ltchiptool.util.streams import StreamHook

_T_XmodemCB = Optional[Callable[[int, int, int], None]]

ACK = b"\x06"
NAK = b"\x15"

# ROM/loader commands (ACK is 0x06)
CMD_USB = 0x05  # set UART baud rate
CMD_XMD = 0x07  # enter XMODEM mode (RAM/flash write)
CMD_EFS = 0x17  # erase flash sectors
CMD_FRD = 0x20  # read flash sectors (loader only)
CMD_GFS = 0x21  # flash status / JEDEC ID read
CMD_SFS = 0x26  # flash status write
CMD_CRC = 0x27  # flash content checksum
CMD_RWA = 0x31  # read dword

# Flashloader RAM entry point (KM0 SRAM) and the ROM's UART baud rate;
# bench-verified on a BW16 KIT.
AMBD_RAM_ADDRESS = 0x82000
AMBD_ROM_BAUDRATE = 115200
# Flash writes are addressed through the XIP window. Raw offsets overlap the
# loader's own RAM (0x82000) and silently corrupt the transfer (bench: a full
# 4 MB write from 0x0 ACKed every packet yet programmed nothing).
AMBD_FLASH_ADDRESS = 0x08000000

AMBD_BLOCK_SIZE = 0x1000

# The ROM selects a baud by index into this table, starting at 0x0D.
AMBD_BAUDRATE_TABLE = [
    115200,
    128000,
    153600,
    230400,
    380400,
    460800,
    500000,
    921600,
    1000000,
    1382400,
    1444400,
    1500000,
    1843200,
    2000000,
    2100000,
    2764800,
    3000000,
    3250000,
    3692300,
    3750000,
    4000000,
    6000000,
]


def checksum32(data: bytes) -> int:
    """CMD_CRC reference value: 32-bit sum of little-endian dwords."""
    remainder = len(data) & 3
    total = 0
    for (dword,) in struct.iter_unpack("<I", data[: len(data) - remainder]):
        total = (total + dword) & 0xFFFFFFFF
    for i in range(remainder):
        total = (total + (data[len(data) - remainder + i] << (i * 8))) & 0xFFFFFFFF
    return total


class AmbDAddressHook(StreamHook):
    """Prepends the 4-byte LE destination address to every XMODEM packet."""

    def __init__(self, address: int):
        super().__init__()
        self.address = address

    def read(self, io: IO[bytes], n: int) -> bytes:
        data = super().read(io, n)
        if not data:
            return b""
        data = struct.pack("<I", self.address) + data
        self.address += n
        # pad to force sending N+4 packet size
        data = data.ljust(n + 4, b"\xff")
        return data


class AmbDTool(SerialToolBase):
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
            getc=self.xm_getc,
            putc=self.xm_putc,
            mode="xmodem1k",
        )
        self.loader_running = False

    #############################
    # Xmodem serial port access #
    #############################

    def xm_getc(self, size, timeout=1):
        try:
            return self.read(size) or None
        except TimeoutError:
            return None

    def xm_putc(self, data, timeout=1):
        self.write(data)
        return len(data)

    #########################################
    # Basic commands - public low-level API #
    #########################################

    def command(self, data: bytes, ack: int = ACK[0]) -> bool:
        """Send a command and scan the response stream for its ack byte."""
        self.write(data)
        for _ in range(5):
            try:
                response = self.read(1)
            except TimeoutError:
                return False
            if response and response[0] == ack:
                return True
        return False

    def read_regs(self, address: int, size: int) -> Optional[bytes]:
        """Read memory dwords via CMD_RWA; also the ROM-alive probe."""
        result = b""
        while size > 0:
            self.flush()
            self.write(struct.pack("<BI", CMD_RWA, address))
            if not self.command(b"", ack=CMD_RWA):
                return None
            try:
                data = self.read(5)
            except TimeoutError:
                return None
            if len(data) != 5 or data[4] != NAK[0]:
                return None
            result += data[:4]
            size -= 4
            address += 4
        return result

    def change_baudrate(self, baudrate: int) -> None:
        if self.s.baudrate == baudrate:
            return
        index = 0x0D + AMBD_BAUDRATE_TABLE.index(baudrate)
        debug(f"Setting baud {baudrate} (index {index:#04x})")
        if not self.command(struct.pack("<BB", CMD_USB, index)):
            raise RuntimeError("No ACK for baud rate change")
        # the ACK arrives at the old rate; only then switch the port
        self.set_baudrate(baudrate)

    #########################
    # Flashloader handling  #
    #########################

    def memory_write(
        self,
        address: int,
        data: bytes,
        callback: _T_XmodemCB = None,
    ) -> None:
        """XMODEM-write a block to RAM or flash (loader decides by address)."""
        if not self.command(struct.pack("<B", CMD_XMD)):
            raise RuntimeError("No ACK for XMODEM handshake")
        stream = BytesIO(data)
        hook = AmbDAddressHook(address)
        hook.attach(stream)
        debug(f"XMODEM: transmitting {len(data)} bytes to 0x{address:X}")
        self.push_timeout(1.0)
        try:
            if not self.xm.send(stream, callback=callback):
                raise RuntimeError("XMODEM transmission failed")
        finally:
            hook.detach(stream)
            self.pop_timeout()

    def transfer_abort(self) -> None:
        """Cancel any in-flight XMODEM transfer left over from a prior run."""
        try:
            self.flush()
            # five CANs, like a cancelling XMODEM endpoint - a loader waiting
            # for packet data ignores shorter bursts (bench: two were not
            # enough to unwedge it)
            self.write(b"\x18" * 5)
            sleep(0.3)
            self.flush()
        except TimeoutError:
            pass

    def close(self) -> None:
        # Leave the loader at the ROM baudrate: the next session opens there and
        # bytes at a mismatched rate parse as garbage commands (a loader left at
        # 460800 wedged the follow-up run). Blind request, as the reference tool does.
        try:
            if self.loader_running and self.s.baudrate != AMBD_ROM_BAUDRATE:
                self.write(struct.pack("<BB", CMD_USB, 0x0D))
                sleep(0.1)
        except Exception:
            pass
        super().close()

    def loader_ensure(self, loader: bytes) -> None:
        """Upload the RAM flashloader unless it is already running."""
        if self.loader_running:
            return
        self.transfer_abort()
        regs = self.read_regs(AMBD_RAM_ADDRESS, 4)
        if regs is None:
            # a previous run may have left the loader at a faster rate
            for baudrate in (460800, 921600):
                debug(f"No answer at {self.s.baudrate}, probing {baudrate}")
                self.set_baudrate(baudrate)
                self.transfer_abort()
                regs = self.read_regs(AMBD_RAM_ADDRESS, 4)
                if regs is not None:
                    break
        if regs is None:
            raise RuntimeError("ROM not answering - check download mode and wiring")
        if regs == loader[:4]:
            info("RAM flashloader is already uploaded")
            self.loader_running = True
            return
        info(f"Uploading flashloader ({len(loader)} bytes) to 0x{AMBD_RAM_ADDRESS:X}")
        self.memory_write(AMBD_RAM_ADDRESS, loader)
        sleep(0.1)
        self.loader_running = True

    def flash_read_id(self) -> bytes:
        """Read the JEDEC flash ID; also proves the loader is running."""
        self.flush()
        if not self.command(struct.pack("<BBB", CMD_GFS, 0x9F, 0x03), ack=CMD_GFS):
            raise RuntimeError("No response to flash ID read")
        flash_id = self.read(3)
        if len(flash_id) != 3:
            raise RuntimeError(f"Flash ID length invalid: {flash_id!r}")
        return flash_id

    #######################################
    # Flash-related commands - public API #
    #######################################

    def flash_checksum(self, offset: int, length: int) -> int:
        """Ask the loader for the checksum of a flash range."""
        self.flush()
        pkt = struct.pack("<B3s3s", CMD_CRC, inttole24(offset), inttole24(length))
        # the loader reads the whole range from SPI flash before answering;
        # scale the timeout with the range (a full 4 MB takes several seconds)
        self.push_timeout(max(2.0, length / 0x400000 * 10.0))
        try:
            if not self.command(pkt, ack=CMD_CRC):
                raise RuntimeError("No response to flash checksum command")
            data = self.read(4)
        finally:
            self.pop_timeout()
        if len(data) != 4:
            raise RuntimeError(f"Checksum length invalid: {data!r}")
        return letoint(data)

    def flash_erase(self, offset: int, length: int) -> None:
        """Erase whole 4KB sectors covering offset..offset+length."""
        count = (length + AMBD_BLOCK_SIZE - 1) // AMBD_BLOCK_SIZE
        offset = align_down(offset, AMBD_BLOCK_SIZE)
        debug(f"Erasing {count} sectors at 0x{offset:X}")
        pkt = struct.pack("<B3s2s", CMD_EFS, inttole24(offset), inttole16(count))
        self.push_timeout(max(self.read_timeout, 0.2 * count))
        try:
            if not self.command(pkt):
                raise RuntimeError(f"No ACK for sector erase at 0x{offset:X}")
        finally:
            self.pop_timeout()

    def _xmodem_receive(self, length: int) -> bytes:
        """ACK-paced XMODEM-1K receive with 8-bit checksums.

        The flashloader transmits without waiting for an initiation byte and
        pads the tail with 0xFF; packets are STX seq ~seq <1024 B> <sum>.
        """
        SOH, STX, EOT, CAN = 0x01, 0x02, 0x04, 0x18
        result = b""
        sequence = 1
        errors = 0
        self.push_timeout(2.0)
        try:
            while True:
                lead = self.read(1)[0]
                if lead == EOT:
                    self.write(ACK)
                    break
                if lead == CAN:
                    raise RuntimeError("Transfer cancelled by the loader")
                if lead not in (SOH, STX):
                    raise RuntimeError(f"Bad packet start: 0x{lead:02X}")
                size = 1024 if lead == STX else 128
                header = self.read(2)
                payload = self.read(size)
                check = self.read(1)[0]
                if header[0] == ((sequence - 1) & 0xFF) and header[1] == (
                    0xFF - ((sequence - 1) & 0xFF)
                ):
                    # duplicate of the previous packet - ACK and drop
                    self.write(ACK)
                    continue
                if (
                    header[0] != (sequence & 0xFF)
                    or header[1] != 0xFF - (sequence & 0xFF)
                    or sum(payload) & 0xFF != check
                ):
                    errors += 1
                    if errors > self.retry_count:
                        raise RuntimeError(
                            f"Too many receive errors at packet {sequence}"
                        )
                    self.flush()
                    self.write(NAK)
                    continue
                errors = 0
                result += payload
                self.write(ACK)
                sequence += 1
                if len(result) >= length:
                    # tail padding may extend past the requested length;
                    # keep ACK-ing until EOT
                    continue
        finally:
            self.pop_timeout()
        if len(result) < length:
            raise RuntimeError(f"Transfer ended early: {len(result)}/{length} bytes")
        return result[:length]

    def flash_read(
        self,
        offset: int,
        length: int,
        verify: bool = True,
    ) -> Generator[bytes, None, None]:
        """Read flash content, in whole 4KB sectors, via loader XMODEM."""
        offset = align_down(offset, AMBD_BLOCK_SIZE)
        length = align_up(length, AMBD_BLOCK_SIZE)
        count = length // AMBD_BLOCK_SIZE

        def dump():
            self.flush()
            verbose(f"<- FLASH_READ(0x{offset:X}, {count} sectors)")
            self.write(
                struct.pack("<B3s2s", CMD_FRD, inttole24(offset), inttole16(count))
            )
            # The loader starts the XMODEM transfer immediately - it does not
            # wait for an initiation byte (bench: STX arrives unprompted).
            data = self._xmodem_receive(length)
            for start in range(0, length, AMBD_BLOCK_SIZE):
                yield data[start : start + AMBD_BLOCK_SIZE]

        received = b""
        for chunk in retry_generator(
            retries=self.retry_count,
            doc=f"Data read error at 0x{offset:X}",
            func=dump,
            onerror=self.flush,
        ):
            if verify:
                received += chunk
            yield chunk

        if verify:
            chip_sum = self.flash_checksum(offset, length)
            local_sum = checksum32(received)
            if chip_sum != local_sum:
                raise ValueError(
                    f"Flash checksum mismatch at 0x{offset:X}+0x{length:X}: "
                    f"chip 0x{chip_sum:08X} != local 0x{local_sum:08X}"
                )
            debug(f"Flash read verified at 0x{offset:X} (0x{local_sum:08X})")

    def flash_write(
        self,
        offset: int,
        data: bytes,
        verify: bool = True,
        callback: _T_XmodemCB = None,
    ) -> None:
        """Erase + write + checksum-verify a flash range."""
        self.flash_erase(offset, len(data))
        self.memory_write(
            AMBD_FLASH_ADDRESS | (offset & 0xFFFFFF), data, callback=callback
        )
        sleep(0.15)
        if self.s.baudrate != AMBD_ROM_BAUDRATE:
            # after a flash write the loader falls back to 115200 on its own
            # (bench: CMD_CRC gets no answer at the old rate); blind-request
            # 115200, follow it, then renegotiate the working rate
            working = self.s.baudrate
            self.write(struct.pack("<BB", CMD_USB, 0x0D))
            self.set_baudrate(AMBD_ROM_BAUDRATE)
            sleep(0.1)
            self.flush()
            self.change_baudrate(working)
        if verify:
            chip_sum = self.flash_checksum(offset, len(data))
            local_sum = checksum32(data)
            if chip_sum != local_sum:
                raise RuntimeError(
                    f"Flash checksum mismatch at 0x{offset:X}: "
                    f"chip 0x{chip_sum:08X} != local 0x{local_sum:08X}"
                )
            debug(f"Flash write verified at 0x{offset:X} (0x{local_sum:08X})")

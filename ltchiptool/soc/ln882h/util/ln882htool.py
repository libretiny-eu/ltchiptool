#  Copyright (c) Etienne Le Cousin 2025-02-23.

from logging import debug, info
from os import path, stat
from tempfile import NamedTemporaryFile
from time import sleep, time
from typing import IO, Callable, Generator, Optional

import click
from ymodem.Socket import ModemSocket

from ltchiptool.util.cli import DevicePortParamType
from ltchiptool.util.serialtool import SerialToolBase

_T_YmodemCB = Optional[Callable[[int, str, int, int], None]]

LN882H_YM_BAUDRATE = 1000000
LN882H_ROM_BAUDRATE = 115200
LN882H_FLASH_ADDRESS = 0x0000000
LN882H_RAM_ADDRESS = 0x20000000
LN882H_BOOTRAM_FILE = "ramcode.bin"


class LN882hTool(SerialToolBase):
    ramcode = False

    def __init__(
        self,
        port: str,
        baudrate: int,
        link_timeout: float = 10.0,
        read_timeout: float = 0.2,
        retry_count: int = 10,
    ):
        super().__init__(port, baudrate, link_timeout, read_timeout, retry_count)
        self.ym = ModemSocket(
            read=lambda size, timeout=2: self.read(size) or None,
            write=lambda data, timeout=2: self.write(data),
            packet_size=128,  # it seems that ramcode doesn't support 1k packets for filename...
        )

    #########################################
    # Private                               #
    #########################################

    # Redefinition of readlines because romloader omit the last '\n' on some cmds...
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
        if response:  # add the last received "line" if any
            yield response
        raise TimeoutError("Timeout in readlines() - no more data received")

    #########################################
    # Basic commands - public low-level API #
    #########################################

    def command(self, cmd: str, waitresp: bool = True) -> str:
        debug(f"cmd: {cmd}")
        self.flush()
        self.write(cmd.encode() + b"\r\n")
        # remove ramcode echo
        if self.ramcode:
            self.read(len(cmd))
        return waitresp and self.resp() or None

    def resp(self) -> str:
        r = []
        try:
            for l in self.readlines():
                r.append(l)
        except TimeoutError:
            pass
        if not r:
            raise TimeoutError("No response")
        debug(f"resp: {r}")
        return r

    def ping(self) -> None:
        self.ramcode = False
        resp = self.command("version")[-1]
        if resp == "RAMCODE":
            self.ramcode = True
        elif len(resp) != 20 or resp[11] != "/":
            raise RuntimeError(f"Incorrect ping response: {resp!r}")

    def disconnect(self) -> None:
        self.sw_reset()

    def link(self) -> None:
        end = time() + self.link_timeout
        while time() < end:
            try:
                self.ping()
                return
            except (RuntimeError, TimeoutError):
                pass
        raise TimeoutError("Timeout while linking")

    def sw_reset(self) -> None:
        self.command("reboot", waitresp=False)

    def change_baudrate(self, baudrate: int) -> None:
        if self.s.baudrate == baudrate:
            return
        self.flush()
        self.command(f"baudrate {baudrate}", waitresp=False)
        self.flush()
        self.set_baudrate(baudrate)

    ###############################################
    # Flash-related commands - for internal usage #
    ###############################################

    def ram_boot(
        self,
        callback: _T_YmodemCB = None,
    ) -> None:
        if self.ramcode:
            return

        info("Loading RAM Code...")
        ramcode_file = path.join(path.dirname(__file__), LN882H_BOOTRAM_FILE)
        ramcode_size = stat(ramcode_file).st_size

        self.command(
            f"download [rambin] [0x{LN882H_RAM_ADDRESS:X}] [{ramcode_size}]",
            waitresp=False,
        )

        self.push_timeout(3)
        debug(f"YMODEM: transmitting to 0x{LN882H_RAM_ADDRESS:X}")
        if not self.ym.send([ramcode_file], callback=callback):
            self.pop_timeout()
            raise RuntimeError("YMODEM transmission failed")
        info("RAM Code successfully loaded.")
        self.pop_timeout()

        # wait for boot start
        sleep(2)
        self.link()

        if not self.ramcode:
            raise RuntimeError("RAM boot failed")

    #######################################
    # Memory-related commands - public API #
    #######################################

    def flash_read(
        self,
        offset: int,
        length: int,
        verify: bool = True,
        chunk_size: int = 256,  # maximum supported chunk size
    ) -> Generator[bytes, None, None]:
        self.link()
        if not self.ramcode:
            self.ram_boot()

        if chunk_size > 256:
            raise RuntimeError(
                f"Chunk size {chunk_size} exceeds the maximum allowed (256)"
            )

        for start in range(offset, offset + length, chunk_size):
            count = min(start + chunk_size, offset + length) - start
            debug(f"Dumping bytes: start=0x{start:X}, count=0x{count:X}")

            resp = self.command(f"flash_read 0x{start:X} 0x{count:X}")[-1]
            data = bytearray.fromhex(resp.decode())

            valid, data = self.ym._verify_recv_checksum(True, data)
            if verify and not valid:
                raise RuntimeError(f"Invalid checksum")

            yield data

    def flash_write(
        self,
        offset: int,
        stream: IO[bytes],
        callback: _T_YmodemCB = None,
    ) -> None:
        self.link()
        prev_baudrate = self.s.baudrate
        if not self.ramcode:
            self.ram_boot()

        self.change_baudrate(LN882H_YM_BAUDRATE)
        self.link()

        self.command(f"startaddr 0x{offset:X}")

        # Convert stream to temporary file before sending with YMODEM
        with NamedTemporaryFile(delete=False) as f:
            f.write(stream.getbuffer())

        self.command(f"upgrade", waitresp=False)

        self.push_timeout(3)
        debug(f"YMODEM: transmitting to 0x{offset:X}")
        if not self.ym.send([f.name], callback=callback):
            self.change_baudrate(prev_baudrate)
            self.pop_timeout()
            raise RuntimeError("YMODEM transmission failed")

        self.link()

        self.change_baudrate(prev_baudrate)
        self.pop_timeout()
        info("Flash Successful.")


@click.command(
    help="LN882H flashing tool",
)
@click.option(
    "-d",
    "--device",
    help="Target device port (default: auto detect)",
    type=DevicePortParamType(),
    default=(),
)
def cli(device: str):
    ln882h = LN882HTool(port=device, baudrate=LN882H_ROM_BAUDRATE)
    info("Linking...")
    ln882h.link()

    info("Loading Ram code...")
    ln882h.ram_boot()

    flash_info = ln882h.command("flash_info")[-1]
    info(f"Received flash info: {flash_info}")

    info("Disconnecting...")
    ln882h.disconnect()


if __name__ == "__main__":
    cli()

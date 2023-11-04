#  Copyright (c) Kuba Szczodrzyński 2023-10-30.

import logging
import struct
from enum import IntEnum
from hashlib import md5
from io import BytesIO
from logging import debug, info, warning
from time import sleep, time
from typing import IO, Callable, Generator, Optional

import click
from xmodem import XMODEM

from ltchiptool.util.cli import DevicePortParamType
from ltchiptool.util.intbin import align_down, align_up, inttole16, inttole24, inttole32
from ltchiptool.util.logging import LoggingHandler, verbose
from ltchiptool.util.misc import retry_generator, sizeof
from ltchiptool.util.serialtool import SerialToolBase
from ltchiptool.util.streams import StreamHook

from .ambzcode import AmbZCode

_T_XmodemCB = Optional[Callable[[int, int, int], None]]

ACK = b"\x06"
NAK = b"\x15"

AMBZ_ROM_BAUDRATE = 1500000
AMBZ_DIAG_BAUDRATE = 115200
AMBZ_FLASH_ADDRESS = 0x8000000
AMBZ_RAM_ADDRESS = 0x10002000
AMBZ_GREETING_TEXT = b"AmbZTool_Marker!"
AMBZ_EFUSE_PHYSICAL_SIZE = 256
AMBZ_EFUSE_LOGICAL_SIZE = 512

AMBZ_CHIP_TYPE = {
    0xE0: "RTL8710BL",  # ???
    0xFF: "RTL8710BN",  # CHIPID_8710BN / QFN32
    0xFE: "RTL8710BU",  # CHIPID_8710BU / QFN48
    0xF6: "RTL8710BX",  # found on an actual RTL8710BX
    0xFB: "RTL8710L0",  # CHIPID_8710BN_L0 / QFN32
    0xFD: "RTL8711BN",  # CHIPID_8711BN / QFN48
    0xFC: "RTL8711BU",  # CHIPID_8711BG / QFN68
}

AMBZ_BAUDRATE_TABLE = [
    110,
    300,
    600,
    1200,
    2400,
    4800,
    9600,
    14400,
    19200,
    28800,
    38400,
    57600,
    76800,
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


class AmbZCommand(IntEnum):
    SET_BAUD_RATE = 0x05
    FLASH_ERASE = 0x17
    FLASH_READ = 0x19
    FLASH_GET_STATUS = 0x21
    FLASH_SET_STATUS = 0x26
    XMODEM_HANDSHAKE = 0x07
    XMODEM_CAN = 0x18


class AmbZAddressHook(StreamHook):
    def __init__(self, address: int):
        super().__init__()
        self.address = address

    def read(self, io: IO[bytes], n: int) -> bytes:
        # read a data packet
        data = super().read(io, n)
        if not data:
            return b""
        # prepend address bytes
        data = inttole32(self.address) + data
        # increment saved address
        self.address += n
        # add padding to force sending N+4 packet size
        data = data.ljust(n + 4, b"\xFF")
        return data


class AmbZTool(SerialToolBase):
    xm_send_code: Optional[bytes] = None
    xm_fake_ack: bool = False

    def __init__(
        self,
        port: str,
        baudrate: int,
        link_timeout: float = 10.0,
        read_timeout: float = 0.6,
        retry_count: int = 10,
        quiet_timeout: float = 10.0,
    ):
        super().__init__(port, baudrate, link_timeout, read_timeout, retry_count)
        LoggingHandler.get().attach(logging.getLogger("xmodem.XMODEM"))
        self.xm = XMODEM(
            getc=self.xm_getc,
            putc=self.xm_putc,
            mode="xmodem1k",
        )
        self.quiet_timeout = quiet_timeout

    #############################
    # Xmodem serial port access #
    #############################

    def xm_getc(self, size, _=1):
        if self.xm_send_code:
            code = self.xm_send_code
            self.xm_send_code = None
            return code
        return self.read(size) or None

    def xm_putc(self, data, _=1):
        self.write(data)
        if self.xm_fake_ack and data == b"\x04":  # EOT
            self.xm_send_code = ACK

    #########################################
    # Basic commands - public low-level API #
    #########################################

    def disconnect(self) -> None:
        # try to enter Loud-Handshake mode
        command = [
            # - Xmodem -> Handshake
            # - Loud-Handshake -> Quiet-Handshake
            AmbZCommand.XMODEM_CAN,
            # - Handshake -> Xmodem
            AmbZCommand.XMODEM_HANDSHAKE,
            # - Xmodem -> Loud-Handshake (resets baud rate)
            AmbZCommand.XMODEM_CAN,
        ]
        self.write(bytes(command))

    def link(self) -> None:
        # clear any data before linking
        self.flush()
        handshake = b""
        end = time() + self.link_timeout
        while time() < end:
            # check if we're in Loud-Handshake mode
            try:
                handshake += self.read(8)
            except TimeoutError:
                pass
            handshake = handshake[-4:]
            if len(handshake) == 4 and all(c == NAK[0] for c in handshake):
                break
            self.disconnect()
            sleep(0.1)
            self.set_baudrate(AMBZ_ROM_BAUDRATE)
        else:
            raise TimeoutError("Timeout while linking")

        self.loud_handshake()

    def quiet_handshake(self) -> None:
        self.flush()
        self.push_timeout(0.1)
        end = time() + self.quiet_timeout
        while time() < end:
            self.write(ACK)
            # discard everything from Loud-Handshake
            try:
                self.read(max_count=4)
            except TimeoutError:
                break
        else:
            self.pop_timeout()
            raise TimeoutError("Timed out waiting for Quiet-Handshake")
        self.pop_timeout()

    def loud_handshake(self) -> None:
        self.flush()
        self.write(struct.pack("<B", AmbZCommand.FLASH_GET_STATUS))
        self.read(1)  # discard status byte
        resp = self.read(5)
        if resp[-1] != NAK[0]:
            raise RuntimeError(f"No NAK for Loud-Handshake mode: {resp!r}")

    def change_baudrate(self, baudrate: int) -> None:
        if self.s.baudrate == baudrate:
            return
        self.flush()
        self.write(
            struct.pack(
                "<BB",
                AmbZCommand.SET_BAUD_RATE,
                AMBZ_BAUDRATE_TABLE.index(baudrate),
            )
        )
        # check response code
        self.expect_ack("baud rate change")
        # change Serial port baudrate
        self.set_baudrate(baudrate)
        # enter Loud-Handshake to check if it still works
        self.loud_handshake()

    def expect_ack(self, doc: str) -> None:
        resp = self.read(1)
        if resp != ACK:
            raise RuntimeError(f"No ACK after {doc}: {resp!r}")

    #######################################
    # Flash-related commands - public API #
    #######################################

    def flash_get_status(self) -> int:
        self.write(struct.pack("<B", AmbZCommand.FLASH_GET_STATUS))
        status = self.read(1)[0]
        return status

    def flash_set_status(self, status: int) -> None:
        self.write(struct.pack("<BB", AmbZCommand.FLASH_GET_STATUS, status))
        self.expect_ack("setting flash status")

    def flash_read(
        self,
        offset: int,
        length: int,
        hash_check: bool = True,
        chunk_size: int = 128 * 1024,
    ) -> Generator[bytes, None, None]:
        block_size = 1 << 12
        ack_size = 1 << 10
        ack_per_block = block_size // ack_size
        offset = align_down(offset, 4)
        length = align_up(length, block_size)

        self.loud_handshake()

        digest = md5()
        for start in range(offset, offset + length, chunk_size):
            count = min(start + chunk_size, offset + length) - start
            debug(f"Dumping bytes: start=0x{start:X}, count=0x{count:X}")

            def dump():
                nonlocal start, count

                verbose(f"<- FLASH_READ(0x{start:X}, {count})")
                # make sure there's no NAK in flash readout
                self.quiet_handshake()
                self.write(
                    struct.pack(
                        "<B3s2s",
                        AmbZCommand.FLASH_READ,
                        inttole24(start),  # in bytes
                        inttole16(count >> 12),  # in 4096-byte blocks
                    )
                )

                blocks_left = count // block_size
                for block in range(blocks_left):
                    data = b""
                    for ack in range(ack_per_block):
                        pos = f"block={block}/{blocks_left}, ack={ack}/{ack_per_block}"
                        verbose(f"-> READ({pos})")
                        data += self.read(ack_size)
                        verbose(f"<- ACK({pos})")
                        self.write(ACK)
                    yield data
                    if hash_check:
                        digest.update(data)
                    # increment offset and length for subsequent error retries
                    start += len(data)
                    count -= len(data)
                # force Quiet-Handshake mode
                self.write(ACK)

            def dump_error():
                # try to skip all chunks
                blocks_left = count // block_size
                warning(
                    f"Dumping failed at 0x{start:X}, "
                    f"discarding {blocks_left} blocks..."
                )
                self.write(ACK * (blocks_left + 1))

            yield from retry_generator(
                retries=self.retry_count,
                doc=f"Data read error at 0x{start:X}",
                func=dump,
                onerror=dump_error,
            )

        self.loud_handshake()

        if hash_check:
            debug(f"Final hash check: start=0x{offset:X}, count=0x{length:X}")
            hash_final = digest.digest()
            hash_expected = self.ram_boot_read(
                AmbZCode.read_data_md5(
                    address=AMBZ_FLASH_ADDRESS | offset,
                    length=length,
                )
                + AmbZCode.print_data(16)
            )
            if hash_final != hash_expected:
                raise ValueError(
                    f"Chip MD5 value does not match calculated "
                    f"value (at 0x{offset:X}+0x{length:X}). Expected: "
                    f"{hash_expected.hex()}, calculated: {hash_final.hex()}"
                )

    def memory_write(
        self,
        address: int,
        stream: IO[bytes],
        callback: _T_XmodemCB = None,
        fake_ack: bool = False,
        ram_keep_baudrate: bool = False,
    ) -> None:
        prev_baudrate = self.s.baudrate
        self.loud_handshake()

        hook = AmbZAddressHook(address)
        hook.attach(stream)

        self.write(bytes([AmbZCommand.XMODEM_HANDSHAKE]))
        self.expect_ack("Xmodem handshake")
        # fake a NAK to make xmodem happy
        self.xm_send_code = NAK
        # fake an ACK after EOT to make xmodem very happy
        self.xm_fake_ack = fake_ack

        debug(f"XMODEM: transmitting to 0x{address:X}")
        self.push_timeout(1.0)
        if not self.xm.send(stream, callback=callback):
            hook.detach(stream)
            self.pop_timeout()
            raise RuntimeError("XMODEM transmission failed")
        hook.detach(stream)
        self.pop_timeout()

        if (address >> 24) == 0x08:
            # back to ROM download mode baudrate
            self.set_baudrate(AMBZ_ROM_BAUDRATE)
            # change it again
            self.change_baudrate(prev_baudrate)
            # do handshake, as we're still in download mode
            self.loud_handshake()
        elif (address >> 24) == 0x10 and not ram_keep_baudrate:
            # Diag_UART re-enabled (xmodem_uart_port_deinit())
            # no handshake - download mode is over
            self.set_baudrate(AMBZ_DIAG_BAUDRATE)

    def ram_boot(
        self,
        code: bytes = None,
        address: int = None,
        callback: _T_XmodemCB = None,
        keep_baudrate: bool = False,
    ) -> None:
        ram_start_table = [
            0x100021EE + 1,
            0x1000219A + 1,
            0x100021EE + 1,
            0x100020F4 + 1,
            0x100021EE + 1,
            0x08000540 + 1,
        ]
        if (code and address is not None) or (not code and address is None):
            raise ValueError("Pass 'code' OR 'address'")

        if code:
            ram_start_table[0] = AMBZ_RAM_ADDRESS + len(ram_start_table) * 4
        else:
            ram_start_table[0] = address
        ram_start_table[0] |= 1

        data = struct.pack("<" + "I" * len(ram_start_table), *ram_start_table)
        if code:
            data += code
        self.memory_write(
            AMBZ_RAM_ADDRESS,
            BytesIO(data),
            callback,
            # fake an ACK after EOT, because it's somehow lost after booting to RAM
            fake_ack=True,
            ram_keep_baudrate=keep_baudrate,
        )

    def ram_boot_read(
        self,
        code: bytes,
        timeout: float = 5.0,
        callback: _T_XmodemCB = None,
    ) -> bytes:
        # RAM booting prints messages on Diag_UART at 115200
        # set it now to avoid having to switch
        prev_baudrate = self.s.baudrate
        self.change_baudrate(AMBZ_DIAG_BAUDRATE)

        # find actual response using a marker message
        # wait before printing to let previous bytes through
        code = AmbZCode.print_greeting(delay=0.4, data=AMBZ_GREETING_TEXT) + code
        # go back into download mode after we're done
        code = code + AmbZCode.download_mode()

        # messages printed by the ROM
        msg_pre = AMBZ_GREETING_TEXT
        msg_post = b"UARTIMG_Download"
        # send RAM code, exit download mode (changes baudrate to 115200)
        self.ram_boot(code=code, callback=callback, keep_baudrate=True)

        self.push_timeout(0.1)
        resp = b""
        end = time() + timeout
        while time() < end:
            try:
                resp += self.read()
            except TimeoutError:
                pass
            if msg_post in resp:
                break
        self.pop_timeout()

        if msg_pre in resp:
            resp = resp.partition(msg_pre)[2]
        elif msg_pre[-7:] in resp:
            warning(f"Partial marker message found: {resp!r}")
            resp = resp.partition(msg_pre[-7:])[2]
        else:
            raise RuntimeError(f"Marker message not found: {resp!r}")

        if msg_post in resp:
            resp = resp.partition(msg_post)[0]
        else:
            warning(f"Expected message not found: {resp!r}")

        self.set_baudrate(AMBZ_ROM_BAUDRATE)
        self.loud_handshake()
        if prev_baudrate != AMBZ_ROM_BAUDRATE:
            self.change_baudrate(prev_baudrate)
        return resp


@click.command(
    help="AmebaZ flashing tool",
)
@click.option(
    "-d",
    "--device",
    help="Target device port (default: auto detect)",
    type=DevicePortParamType(),
    default=(),
)
def cli(device: str):
    amb = AmbZTool(port=device, baudrate=AMBZ_ROM_BAUDRATE)
    info("Linking...")
    amb.link()

    chip_info = amb.ram_boot_read(
        AmbZCode.read_chip_id(offset=0)
        + AmbZCode.read_flash_id(offset=1)
        + AmbZCode.print_data(length=4)
    )
    info(f"Received chip info: {chip_info.hex()}")
    chip_id = chip_info[0]
    size_id = chip_info[3]
    info("Chip type: " + AMBZ_CHIP_TYPE.get(chip_id, f"Unknown 0x{chip_id:02X}"))
    if 0x14 <= size_id <= 0x19:
        info("Flash size: " + sizeof(1 << size_id))
    else:
        warning(f"Couldn't process flash ID: got {chip_info!r}")

    info("Disconnecting...")
    amb.disconnect()


if __name__ == "__main__":
    cli()

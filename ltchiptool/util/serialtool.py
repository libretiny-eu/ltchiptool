#  Copyright (c) Kuba Szczodrzyński 2023-10-30.

from time import time
from typing import Generator, List

from serial import Serial

from .logging import verbose


class SerialToolBase:
    prev_timeout_list: List[float]

    def __init__(
        self,
        port: str,
        baudrate: int,
        link_timeout: float = 10.0,
        read_timeout: float = 0.5,
        retry_count: int = 10,
    ):
        self.prev_timeout_list = []
        self.link_timeout = link_timeout
        self.read_timeout = read_timeout
        self.retry_count = retry_count

        self.s = Serial(port, baudrate)

    #################################
    # Serial transmission utilities #
    #################################

    def close(self) -> None:
        self.s.close()
        self.s = None

    def set_baudrate(self, baudrate: int) -> None:
        verbose(f"-- UART: Port baudrate set to {baudrate}")
        self.s.close()
        self.s.baudrate = baudrate
        self.s.open()

    def write(self, data: bytes) -> None:
        self.s.write(data)

    def read(self, count: int = None, max_count: int = None) -> bytes:
        if max_count is not None:
            count = max_count
        response = b""
        end = time() + self.read_timeout
        self.s.timeout = self.read_timeout
        while time() < end:
            to_read = self.s.in_waiting
            if not to_read:
                continue
            if count:
                to_read = min(to_read, count - len(response))
            read = self.s.read(to_read)
            if not read:
                continue
            end = time() + self.read_timeout
            response += read
            if count and len(response) >= count:
                break

        if not response:
            raise TimeoutError(f"Timeout in read({count}) - no data received")
        if not count:
            return response
        response = response[:count]
        if max_count is None and len(response) != count:
            raise TimeoutError(
                f"Timeout in read({count}) - not enough data received ({len(response)})"
            )
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

    def timed_flush(self, timeout: float = 0.5) -> None:
        # try to clean up the serial buffer
        # no data for 0.5 s means that the chip stopped sending bytes
        self.push_timeout(timeout)
        try:
            self.read()  # read all available data
        except TimeoutError:
            pass
        self.pop_timeout()

    def error_flush(self) -> None:
        self.timed_flush()
        # pop timeout of the failing function
        self.pop_timeout()

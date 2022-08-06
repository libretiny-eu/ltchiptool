# Copyright (c) Kuba Szczodrzyński 2022-08-06.

from enum import IntEnum
from io import FileIO
from os import stat
from socket import (
    AF_INET,
    IPPROTO_TCP,
    SO_SNDBUF,
    SOCK_STREAM,
    SOL_SOCKET,
    TCP_NODELAY,
    gethostbyname,
    socket,
)
from typing import Tuple, Union

from ltchiptool.util.intbin import inttobe32

OTA_MAGIC = b"\x6C\x26\xF7\x5C\x45"


def tohex(data: bytes) -> str:
    out = []
    for i in range(len(data)):
        out.append(data[i : i + 1].hex())
    return " ".join(out)


class OTACode(IntEnum):
    RESP_OK = 0
    RESP_REQUEST_AUTH = 1
    RESP_HEADER_OK = 64
    RESP_AUTH_OK = 65
    RESP_UPDATE_PREPARE_OK = 66
    RESP_BIN_MD5_OK = 67
    RESP_RECEIVE_OK = 68
    RESP_UPDATE_END_OK = 69
    RESP_SUPPORTS_COMPRESSION = 70

    ERROR_MAGIC = 128
    ERROR_UPDATE_PREPARE = 129
    ERROR_AUTH_INVALID = 130
    ERROR_WRITING_FLASH = 131
    ERROR_UPDATE_END = 132
    ERROR_INVALID_BOOTSTRAPPING = 133
    ERROR_WRONG_CURRENT_FLASH_CONFIG = 134
    ERROR_WRONG_NEW_FLASH_CONFIG = 135
    ERROR_ESP8266_NOT_ENOUGH_SPACE = 136
    ERROR_ESP32_NOT_ENOUGH_SPACE = 137
    ERROR_NO_UPDATE_PARTITION = 138
    ERROR_UNKNOWN = 255

    VERSION_1_0 = 1
    FEATURE_SUPPORTS_COMPRESSION = 0x01


class ESPHomeUploader:
    file: FileIO
    file_size: int
    file_md5: bytes

    sock: socket
    host: str
    port: int

    password: str = None
    debug: bool = False

    def __init__(
        self,
        file: FileIO,
        md5: bytes,
        host: str,
        port: int,
        password: str = None,
        debug: bool = False,
    ):
        self.file = file
        self.file_size = stat(file.name).st_size
        self.file_md5 = md5
        self.host = host
        self.port = port
        self.password = password
        self.debug = debug

    def dbg(self, *msg):
        if self.debug:
            print(*msg)

    def resolve_host(self):
        self.dbg("Resolving", self.host)
        parts = self.host.split(".")
        if all(map(lambda x: x.isnumeric(), parts)):
            if not all(map(lambda x: int(x) in range(0, 255), parts)):
                raise ValueError(f"Invalid IP address: {self.host}")
            return
        ip_addr = gethostbyname(self.host)
        print(f"|   |-- Resolved {self.host} to {ip_addr}")
        self.host = ip_addr

    def connect(self):
        self.dbg("Connecting to", self.host, self.port)
        self.sock = socket(AF_INET, SOCK_STREAM)
        self.sock.settimeout(10.0)
        try:
            self.sock.connect((self.host, self.port))
        except OSError as e:
            self.sock.close()
            raise RuntimeError(f"Couldn't connect to {self.host}:{self.port} - {e}")
        self.sock.setsockopt(IPPROTO_TCP, TCP_NODELAY, 1)

    def send(self, data: Union[bytes, int]):
        if isinstance(data, int):
            data = bytes([data])
        self.dbg("<-- TX:", tohex(data))
        self.sock.sendall(data)

    def receive(self, *codes: OTACode, size: int = 0) -> Tuple[OTACode, bytes]:
        data = self.sock.recv(1)
        response = OTACode(data[0])
        self.dbg("--> RX:", response.name)
        if response not in codes:
            raise ValueError(f"Received {response.name} instead of {codes}")
        if size == 0:
            return response, b""
        data = self.sock.recv(size)
        self.dbg("--> RX:", tohex(data))
        return response, data

    def upload(self):
        self.resolve_host()
        self.connect()

        self.send(OTA_MAGIC)
        _, ver = self.receive(OTACode.RESP_OK, size=1)
        if ver[0] != OTACode.VERSION_1_0:
            raise ValueError("Invalid OTA version")
        print("|-- Connected to ESPHome")

        self.send(OTACode.FEATURE_SUPPORTS_COMPRESSION)
        features, _ = self.receive(
            OTACode.RESP_HEADER_OK, OTACode.RESP_SUPPORTS_COMPRESSION
        )
        if features == OTACode.RESP_SUPPORTS_COMPRESSION:
            raise NotImplementedError("Compression is not implemented")

        auth, _ = self.receive(OTACode.RESP_AUTH_OK, OTACode.RESP_REQUEST_AUTH)
        if auth == OTACode.RESP_REQUEST_AUTH:
            raise NotImplementedError("Authentication is not implemented")

        self.send(inttobe32(self.file_size))
        self.receive(OTACode.RESP_UPDATE_PREPARE_OK)

        self.send(self.file_md5.hex().encode())
        self.receive(OTACode.RESP_BIN_MD5_OK)

        self.sock.setsockopt(IPPROTO_TCP, TCP_NODELAY, 0)
        self.sock.setsockopt(SOL_SOCKET, SO_SNDBUF, 8192)
        self.sock.settimeout(20.0)

        print("|-- Starting OTA upload")
        while True:
            data = self.file.read(1024)
            if not data:
                break
            self.sock.sendall(data)

        self.sock.setsockopt(IPPROTO_TCP, TCP_NODELAY, 1)
        self.receive(OTACode.RESP_RECEIVE_OK)
        self.receive(OTACode.RESP_UPDATE_END_OK)
        self.send(OTACode.RESP_OK)

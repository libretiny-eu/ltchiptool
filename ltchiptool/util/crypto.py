#  Copyright (c) Kuba Szczodrzyński 2023-3-14.

from logging import debug
from typing import Protocol


class CryptoAES(Protocol):
    def encrypt(self, data: bytes) -> bytes:
        ...

    def decrypt(self, data: bytes) -> bytes:
        ...


def make_aes_crypto(key: bytes, iv: bytes) -> CryptoAES:
    builders = [
        _make_aes_pycryptodomex,
        _make_aes_pycryptodome,
        _make_aes_cryptography,
        _make_aes_pyaes,
    ]
    for builder in builders:
        try:
            return builder(key, iv)
        except (ImportError, ModuleNotFoundError):
            continue
    raise ImportError("No module suitable for AES cryptography found")


def _make_aes_pycryptodome(key: bytes, iv: bytes) -> CryptoAES:
    from Crypto.Cipher import AES

    debug("Using PyCryptodome for OTA encryption")
    return AES.new(key=key, mode=AES.MODE_CBC, iv=iv)


def _make_aes_pycryptodomex(key: bytes, iv: bytes) -> CryptoAES:
    from Cryptodome.Cipher import AES

    debug("Using PyCryptodomex for OTA encryption")
    return AES.new(key=key, mode=AES.MODE_CBC, iv=iv)


def _make_aes_cryptography(key: bytes, iv: bytes) -> CryptoAES:
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    debug("Using Cryptography for OTA encryption")
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    encryptor = cipher.encryptor()
    decryptor = cipher.decryptor()

    class Wrap:
        @staticmethod
        def encrypt(data: bytes) -> bytes:
            return encryptor.update(data) + encryptor.finalize()

        @staticmethod
        def decrypt(data: bytes) -> bytes:
            return decryptor.update(data) + decryptor.finalize()

    return Wrap()


def _make_aes_pyaes(key: bytes, iv: bytes) -> CryptoAES:
    from pyaes import AESModeOfOperationCBC, Decrypter, Encrypter

    debug("Using PyAES for OTA encryption")
    aes = AESModeOfOperationCBC(key=key, iv=iv)
    encrypter = Encrypter(aes)
    decrypter = Decrypter(aes)

    class Wrap:
        @staticmethod
        def encrypt(data: bytes) -> bytes:
            return encrypter.feed(data) + encrypter.feed()

        @staticmethod
        def decrypt(data: bytes) -> bytes:
            return decrypter.feed(data) + decrypter.feed()

    return Wrap()

import gzip
import importlib.util
import unittest
from binascii import crc32
from hashlib import sha256
from io import BytesIO
from struct import pack
from unittest.mock import patch

from ltchiptool.soc.bk72xx.util.binary import BekenBinary
from ltchiptool.soc.bk72xx.util.models import OTACompression, OTAEncryption
from ltchiptool.soc.bk72xx.util.rbl import RBL
from ltchiptool.util.crypto import (
    _make_aes_cryptography,
    _make_aes_pyaes,
    _make_aes_pycryptodome,
    _make_aes_pycryptodomex,
)

# NIST SP 800-38A, F.2.5 AES-256-CBC.
KEY = bytes.fromhex(
    "603deb1015ca71be2b73aef0857d7781" "1f352c073b6108d72d9810a30914dff4"
)
IV = bytes.fromhex("000102030405060708090a0b0c0d0e0f")
PLAINTEXT = bytes.fromhex(
    "6bc1bee22e409f96e93d7e117393172a"
    "ae2d8a571e03ac9c9eb76fac45af8e51"
    "30c81c46a35ce411e5fbc1191a0a52ef"
    "f69f2445df4f9b17ad2b417be66c3710"
)
CIPHERTEXT = bytes.fromhex(
    "f58c4c04d6e5f1ba779eabfb5f7bfbd6"
    "9cfc4e967edb808d679f777bc6702c7d"
    "39f23369a9d9bacfa530e26304231461"
    "b2eb05e2c39be9fcda6c19078c6a9d1b"
)


def available_backends():
    backends = [("pyaes", _make_aes_pyaes)]
    for module, builder in [
        ("Crypto", _make_aes_pycryptodome),
        ("Cryptodome", _make_aes_pycryptodomex),
        ("cryptography", _make_aes_cryptography),
    ]:
        if importlib.util.find_spec(module) is not None:
            backends.append((module, builder))
    return backends


def gzip_at_length(raw, length):
    """Use an ignored gzip extra field to fix the size across zlib versions."""
    stream = gzip.compress(raw, compresslevel=9)
    assert stream[3] == 0
    extra_size = length - len(stream)
    assert extra_size >= 6
    extra = b"LT" + pack("<H", extra_size - 6) + bytes(extra_size - 6)
    return (
        stream[:3]
        + b"\x04"
        + stream[4:10]
        + pack("<H", len(extra))
        + extra
        + stream[10:]
    )


class CryptoAESTest(unittest.TestCase):
    def test_nist_encrypt(self):
        for name, builder in available_backends():
            with self.subTest(backend=name):
                self.assertEqual(builder(KEY, IV).encrypt(PLAINTEXT), CIPHERTEXT)

    def test_nist_decrypt(self):
        for name, builder in available_backends():
            with self.subTest(backend=name):
                self.assertEqual(builder(KEY, IV).decrypt(CIPHERTEXT), PLAINTEXT)

    def test_aligned_lengths_and_padding_like_data(self):
        for length in (0, 16, 32, 4080, 4096, 4112):
            # A raw CBC backend must preserve data that looks like PKCS#7 padding.
            data = bytes([16]) * length
            reference = None
            for name, builder in available_backends():
                with self.subTest(length=length, backend=name):
                    ciphertext = builder(KEY, IV).encrypt(data)
                    self.assertEqual(len(ciphertext), length)
                    self.assertEqual(builder(KEY, IV).decrypt(ciphertext), data)
                    if reference is None:
                        reference = ciphertext
                    self.assertEqual(ciphertext, reference)

    def test_rejects_unaligned_input(self):
        for name, builder in available_backends():
            for method in ("encrypt", "decrypt"):
                for length in (1, 15, 17):
                    with self.subTest(backend=name, method=method, length=length):
                        operation = getattr(builder(KEY, IV), method)
                        # PyAES raises a plain Exception for an invalid block length.
                        with self.assertRaisesRegex(Exception, "block|length|boundary"):
                            operation(bytes(length))

    def test_beken_gzip_at_4096_byte_boundary(self):
        raw = b"".join(sha256(pack("<I", i)).digest() for i in range(65))
        # Two bytes of Beken padding must bring this to exactly 4096.
        stream = gzip_at_length(raw, 4094)
        self.assertEqual(len(stream), 4094)
        self.assertEqual(gzip.decompress(stream), raw)
        reference = None
        for name, builder in available_backends():
            with self.subTest(backend=name):
                header = RBL(
                    encryption=OTAEncryption.AES256,
                    compression=OTACompression.GZIP,
                    timestamp=0,
                )
                with patch(
                    "ltchiptool.soc.bk72xx.util.binary.make_aes_crypto", builder
                ), patch(
                    "ltchiptool.soc.bk72xx.util.binary.gzip.compress",
                    return_value=stream,
                ):
                    image = b"".join(
                        BekenBinary().ota_package(BytesIO(raw), header, KEY, IV)
                    )
                parsed = RBL.deserialize(image[:96])
                self.assertEqual(parsed.data_size, 4096)
                self.assertEqual(len(image), 96 + 4096)
                self.assertEqual(parsed.data_crc, crc32(image[96:]))
                if reference is None:
                    reference = image
                self.assertEqual(image, reference)
                for reader_name, reader in available_backends():
                    with self.subTest(reader=reader_name), patch(
                        "ltchiptool.soc.bk72xx.util.binary.make_aes_crypto", reader
                    ):
                        decoded = b"".join(
                            BekenBinary().ota_unpackage(
                                BytesIO(image[96:]), parsed, KEY, IV
                            )
                        )
                        self.assertEqual(decoded, raw)


if __name__ == "__main__":
    unittest.main()

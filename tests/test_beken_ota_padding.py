import gzip
import unittest
from binascii import crc32
from io import BytesIO
from unittest.mock import patch

from pyaes import AESModeOfOperationCBC, Encrypter
from test_crypto import IV, KEY, available_backends, gzip_at_length

from ltchiptool.soc.bk72xx.util.binary import BekenBinary
from ltchiptool.soc.bk72xx.util.models import OTACompression, OTAEncryption
from ltchiptool.soc.bk72xx.util.rbl import RBL
from ltchiptool.util.crypto import _make_aes_pyaes


class LegacyPyAES:
    """Reproduce the old adapter's implicit extra PKCS#7 padding."""

    def __init__(self, key, iv):
        self.encrypter = Encrypter(AESModeOfOperationCBC(key=key, iv=iv))

    def encrypt(self, data):
        return self.encrypter.feed(data) + self.encrypter.feed()


class BekenOTAPaddingTest(unittest.TestCase):
    def assert_decodes_with_all_backends(self, image, expected):
        header = RBL.deserialize(image[:96])
        self.assertEqual(header.data_size, len(image) - 96)
        self.assertEqual(header.data_crc, crc32(image[96:]))
        for name, reader in available_backends():
            with self.subTest(reader=name), patch(
                "ltchiptool.soc.bk72xx.util.binary.make_aes_crypto", reader
            ):
                actual = b"".join(
                    BekenBinary().ota_unpackage(BytesIO(image[96:]), header, KEY, IV)
                )
                self.assertEqual(actual, expected)

    def test_gzip_old_and_new_images_at_every_padding_length(self):
        raw = b"legacy firmware example" * 4
        for remainder in range(16):
            stream = gzip_at_length(raw, 80 + remainder)
            self.assertEqual(len(stream), 80 + remainder)
            self.assertEqual(gzip.decompress(stream), raw)
            for writer in (LegacyPyAES, _make_aes_pyaes):
                with self.subTest(remainder=remainder, writer=writer.__name__):
                    header = RBL(
                        encryption=OTAEncryption.AES256,
                        compression=OTACompression.GZIP,
                        timestamp=0,
                    )
                    with patch(
                        "ltchiptool.soc.bk72xx.util.binary.make_aes_crypto", writer
                    ), patch(
                        "ltchiptool.soc.bk72xx.util.binary.gzip.compress",
                        return_value=stream,
                    ):
                        image = b"".join(
                            BekenBinary().ota_package(BytesIO(raw), header, KEY, IV)
                        )
                    # 80..95 gzip bytes all receive padding up to 96 bytes.
                    expected_size = 112 if writer is LegacyPyAES else 96
                    self.assertEqual(header.data_size, expected_size)
                    self.assert_decodes_with_all_backends(image, raw)

    def test_uncompressed_images_preserve_padding_like_plaintext(self):
        for length in range(33):
            raw = bytes([16]) * length
            for writer in (LegacyPyAES, _make_aes_pyaes):
                with self.subTest(length=length, writer=writer.__name__):
                    header = RBL(
                        encryption=OTAEncryption.AES256,
                        compression=OTACompression.NONE,
                        timestamp=0,
                    )
                    with patch(
                        "ltchiptool.soc.bk72xx.util.binary.make_aes_crypto", writer
                    ):
                        image = b"".join(
                            BekenBinary().ota_package(BytesIO(raw), header, KEY, IV)
                        )
                    self.assert_decodes_with_all_backends(image, raw)

    def test_gzip_rejects_invalid_legacy_padding_and_corruption(self):
        raw = b"legacy firmware example" * 4
        stream = gzip_at_length(raw, 94)
        corrupt = bytearray(stream)
        corrupt[-8] ^= 1  # Gzip CRC, with the encrypted payload still well formed.
        cases = {
            "invalid inner padding": stream + b"\x03\x02" + b"\x10" * 16,
            "three padding layers": stream + b"\x02\x02" + b"\x10" * 32,
            "outer padding is not a full block": stream + b"\x01\x01",
            "gzip CRC mismatch": bytes(corrupt) + b"\x02\x02" + b"\x10" * 16,
        }
        for label, plaintext in cases.items():
            ciphertext = _make_aes_pyaes(KEY, IV).encrypt(plaintext)
            header = RBL(
                encryption=OTAEncryption.AES256,
                compression=OTACompression.GZIP,
                raw_size=len(raw),
            )
            for name, reader in available_backends():
                with self.subTest(case=label, reader=name), patch(
                    "ltchiptool.soc.bk72xx.util.binary.make_aes_crypto", reader
                ):
                    with self.assertRaises(OSError):
                        b"".join(
                            BekenBinary().ota_unpackage(
                                BytesIO(ciphertext), header, KEY, IV
                            )
                        )

    def test_uncompressed_rejects_invalid_legacy_padding(self):
        raw = b"A" * 14
        for tail in (b"\x03\x02", b"\x02\x02" + b"\x10" * 16):
            ciphertext = _make_aes_pyaes(KEY, IV).encrypt(raw + tail + b"\x10" * 16)
            header = RBL(
                encryption=OTAEncryption.AES256,
                compression=OTACompression.NONE,
                raw_size=len(raw),
            )
            with self.assertRaisesRegex(ValueError, "Invalid legacy AES padding"):
                b"".join(
                    BekenBinary().ota_unpackage(BytesIO(ciphertext), header, KEY, IV)
                )

    def test_unencrypted_gzip_does_not_use_legacy_padding_fallback(self):
        raw = b"unencrypted image"
        stream = gzip.compress(raw)
        header = RBL(compression=OTACompression.GZIP, raw_size=len(raw))
        self.assertEqual(
            b"".join(BekenBinary().ota_unpackage(BytesIO(stream), header)), raw
        )
        with self.assertRaises(OSError):
            b"".join(
                BekenBinary().ota_unpackage(
                    BytesIO(stream + b"\x02\x02" + b"\x10" * 16), header
                )
            )


if __name__ == "__main__":
    unittest.main()

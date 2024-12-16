#  Copyright (c) Martin Prokopič 2024-12-02

from .models.images import IMAGE_PUBLIC_KEY_OFFSET, IMAGE_SIGNATURE_OFFSET


def patch_firmware_for_ota(data: bytes) -> bytes:
    copy = bytearray(data)
    copy[IMAGE_SIGNATURE_OFFSET] ^= 0xFF  # negate first signature byte
    copy[IMAGE_PUBLIC_KEY_OFFSET] ^= 0xFF  # negate first pubkey byte
    return bytes(copy)

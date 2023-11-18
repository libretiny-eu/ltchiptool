#  Copyright (c) Kuba Szczodrzyński 2023-11-7.

from io import BytesIO


def efuse_physical_to_logical(efuse: bytes) -> bytes:
    efuse = BytesIO(efuse)
    logical = bytearray([0xFF] * 512)

    def copy_words(cell_idx: int, word_map: int):
        logi_addr = 8 * cell_idx
        for i in range(0, 4):
            if not (word_map & (1 << i)):
                logical[logi_addr] = efuse.read(1)[0]
                logical[logi_addr + 1] = efuse.read(1)[0]
            logi_addr += 2

    while True:
        header = efuse.read(1)[0]
        if header == 0xFF:
            break
        if (header & 0x1F) != 0xF:
            copy_words(
                cell_idx=header >> 4,
                word_map=header & 0xF,
            )
            continue

        header_ext = efuse.read(1)[0]
        if (header_ext & 0xF) == 0xF:
            continue
        if header_ext & 0x80:
            if not (header_ext & 1):
                efuse.read(2)
            if not (header_ext & 2):
                efuse.read(2)
            if not (header_ext & 4):
                efuse.read(2)
            if not (header_ext & 8):
                efuse.read(2)
            continue

        copy_words(
            cell_idx=(header >> 5) | ((header_ext & 0xF0) >> 1),
            word_map=header_ext & 0xF,
        )
    return logical

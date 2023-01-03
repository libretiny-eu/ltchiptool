# Copyright 2022 Kjell Braden
# licensed under MIT License

from abc import ABC
from dataclasses import dataclass
from enum import IntEnum
from io import FileIO
from logging import info, warning
from struct import pack

from elftools.elf.elffile import ELFFile
from Cryptodome.Hash import HMAC, SHA256

from ltchiptool import SocInterface
from ltchiptool.util import chname, peek
from ltchiptool.util.intbin import pad_data, pad_up


LEN_HDR_IMG = 0x60
LEN_HDR_SEC = 0x60
LEN_FST = 0x60

MARKER_UNSIGNED = (
    b"LibreTuyaAmebaZ2"
    b"\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a\x0b\x0c\x0d\x0e\x0f"
)
assert len(MARKER_UNSIGNED) == 32


def mac(key: bytes, buf: bytes) -> bytes:
    h = HMAC.new(key, digestmod=SHA256)
    h.update(buf)
    return h.digest()


class ImageType(IntEnum):
    PARTAB = 0
    BOOT = 1
    FWHS_S = 2
    FWHS_NS = 3
    FWLS = 4
    ISP = 5
    VOE = 6
    WLN = 7
    XIP = 8
    WOWLN = 10
    CINIT = 11
    CPFW = 9
    UNKNOWN = 63


class SectionType(IntEnum):
    UNSET = 0x00
    DTCM = 0x80
    ITCM = 0x81
    SRAM = 0x82
    PSRAM = 0x83
    LPDDR = 0x84
    XIP = 0x85
    UNKNOWN = 0xFF


@dataclass
class Section:
    type: SectionType
    data: bytes
    section_base: int
    entry_point: int = 0xFFFFFFFF

    @property
    def entry_hdr(self) -> bytes:
        return pad_data(
            pack("<III", len(self.data), self.section_base, self.entry_point), 32, 0xFF
        )


@dataclass
class SubImage:
    type: ImageType
    sections: list[Section]
    serial: int


@dataclass
class Image:
    subs: list[SubImage]
    pubkeys: list[bytes]

    def __post_init__(self):
        while len(self.pubkeys) < 6:
            self.pubkeys.append(b"\xff" * 32)

        if len(self.pubkeys) > 6:
            raise ValueError("too many pubkeys")

        if not all(len(pk) == 32 for pk in self.pubkeys):
            raise ValueError("pubkeys have invalid length")


def build_section(s: Section) -> bytearray:
    sect_hdr = pack(
        "<IIBBBB4x8sB7x16s16s32x",
        len(s.data) + 0x20,
        0xFFFFFFFF,
        s.type,
        0,  # SCE disabled
        0,  # xip page size
        0,  # xip block size
        bytes(range(8)),  # valid pattern
        0,  # flags (no xip key)
        b"\xff" * 16,  # xip_key
        b"\xff" * 16,  # xip_iv
    )
    assert len(sect_hdr) == LEN_HDR_SEC

    return bytearray(sect_hdr + s.entry_hdr + pad_data(s.data, 32, 0x00))


def build_subimage(img: SubImage) -> bytearray:
    fst = pack(
        "<HHI8s4xBB10x32s16s16x",
        1,  # enc_algo
        1,  # hash_algo
        0,  # part_size??
        bytes(range(8)),  # valid pattern
        0,  # flags (not hashed, not encrypted)
        0,  # key_valid (no cipher key)
        b"\xff" * 32,  # cipher_key
        b"\xff" * 16,  # cipher_iv
    )

    assert len(fst) == LEN_FST
    sects = [build_section(s) for s in img.sections]

    for sect in sects[:-1]:
        sect[4:8] = len(sect).to_bytes(4, "little")

    sects_raw = b"".join(sects)
    assert len(sects_raw) % 32 == 0, len(sects_raw)

    hdr = pack(
        "<IIBBBB8xI8x32s32s",
        len(fst) + len(sects_raw),
        0xFFFFFFFF,
        img.type,
        0x00,  # encrypted?
        0x00,  # 00 for fw images, ff for parttbl and boot
        0x00,  # user keys valid (bits 0 and 1)
        img.serial,
        b"\xff" * 32,  # user_key1
        b"\xff" * 32,  # user_key2
    )

    assert len(hdr) == LEN_HDR_IMG

    return bytearray(hdr + fst + sects_raw)


def build(hash_key: bytes | None, image: Image) -> bytes:
    sub_imgs = [build_subimage(sub) for sub in image.subs]
    buf = bytearray(32 + 32 * 6)

    # pubkeys
    buf[32 : 32 + 32 * 6] = b"".join(image.pubkeys)

    for i, sub in enumerate(sub_imgs):
        # append hash placeholder
        sub += b"\xAA" * 32

        # only set next pointers and padding for all but last image
        if i < len(sub_imgs) - 1:
            padlen = pad_up(len(buf) + len(sub), 0x4000)
            imglen_with_padding = len(sub) + padlen
            sub[4:8] = imglen_with_padding.to_bytes(4, "little")
            sub += b"\x87" * padlen

        buf += sub

    if hash_key:
        # ota_signature
        buf[0:32] = mac(hash_key, sub_imgs[0][:LEN_HDR_IMG])
    else:
        # marker for detect_file_type()
        buf[0:32] = MARKER_UNSIGNED

    return bytes(buf)


def from_elf(
    elf: ELFFile,
    serial: int,
    hash_key: bytes | None = None,
    pubkeys: list[bytes] | None = None,
) -> bytes:
    ram_img = SubImage(
        type=ImageType.FWHS_S,
        serial=serial,
        sections=[],
    )
    xip_imgs = []

    for seg in elf.iter_segments("PT_LOAD"):
        seg_addr = seg["p_vaddr"]
        data = seg.data()

        if not data:
            continue

        if seg_addr & 0xFFF0_0000 == 0x1000_0000:
            # RAM
            ram_img.sections.append(
                Section(
                    type=SectionType.SRAM,
                    section_base=seg_addr,
                    data=seg.data(),
                )
            )
        elif seg_addr & 0xFF00_0000 == 0x9B00_0000:
            # XIP
            # needs separate images for each block
            # as flash placement in image headers needs to fit to memory mapping
            xip_imgs.append(
                SubImage(
                    type=ImageType.XIP,
                    serial=0,
                    sections=[
                        Section(
                            type=SectionType.XIP,
                            section_base=seg_addr,
                            data=seg.data(),
                        )
                    ],
                )
            )
        else:
            warning("ignoring segment in unknown address space: 0x%08x", seg_addr)

    # in bootloader from Dec 5, 2019, it doesn't matter which section or subimage has
    # the entry point, as long as it is in a FWHS_S image.
    # last entry_point != 0xffff_ffff wins
    ram_img.sections[0].entry_point = elf["e_entry"]

    img = Image([ram_img] + xip_imgs, pubkeys=pubkeys or [])

    for sub in img.subs:
        info("sub image %s", sub.type)
        for sect in sub.sections:
            info(
                "  section 0x%08x (entry = 0x%08x): %s",
                sect.section_base,
                sect.entry_point,
                sect.type,
            )

    return build(hash_key, img)


class AmebaZ2Binary(SocInterface, ABC):
    def link2bin(
        self,
        ota1: str,
        ota2: str,
        args: list[str],
    ) -> dict[str, int | None]:
        assert not ota1 and not ota2
        elfs = self.link2elf('', '', args)
        assert elfs.keys() == {1}
        elf = elfs[1]

        return self.elf2bin(elf, 0)

    def elf2bin(
        self,
        input: str,
        ota_idx: int,
    ) -> dict[str, int | None]:

        with ELFFile.load_from_path(input) as elf:
            firmware_raw = from_elf(elf, serial=0xFFFF_FFFF)

        output = chname(input, "firmware_is.bin")
        with open(output, "wb") as f:
            f.write(firmware_raw)

        # TODO None ok here?
        return {output: None}

    def detect_file_type(
        self,
        file: FileIO,
        length: int,
    ) -> tuple[str, int | None, int, int] | None:
        """
        Check if the file is flashable to this SoC.

        :return: a tuple: (file type, offset, skip, length), or None if type unknown
        """
        data = peek(file, size=32)
        if data == MARKER_UNSIGNED:
            return "Realtek AmebaZ2 unsigned OTA image", None, 0, length

        return None

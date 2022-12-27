# Copyright 2022 Kjell Braden
# licensed under MIT License

import argparse
import logging
import typing
from dataclasses import dataclass
from enum import IntEnum
from struct import pack

from elftools.elf.elffile import ELFFile
from Cryptodome.Hash import HMAC, SHA256

from ltchiptool.util.intbin import pad_data, pad_up

LOG = logging.getLogger("elf2bin.amebaz2")


LEN_HDR_IMG = 0x60
LEN_HDR_SEC = 0x60
LEN_FST = 0x60


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
            pack("<III", len(self.data), self.section_base, self.entry_point),
            32,
            0xff
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
        0xffffffff,
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
    fst = pack("<HHI8s4xBB10x32s16s16x",
        1,  # enc_algo
        1,  # hash_algo
        0,  # part_size??
        bytes(range(8)),  # valid pattern
        2,  # flags (hashed, not encrypted)
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

    hdr = pack("<IIBBBB8xI8x32s32s",
        len(fst) + len(sects_raw),
        0xffffffff,
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


def build(hash_key: bytes, image: Image) -> bytes:
    sub_imgs = [build_subimage(sub) for sub in image.subs]
    buf = bytearray(32 + 32 * 6)

    # pubkeys
    buf[32 : 32 + 32 * 6] = b"".join(image.pubkeys)

    sig_offsets = [len(sub) for sub in sub_imgs]
    base = len(buf)

    for sub in sub_imgs[:-1]:
        imglen_with_digest = len(sub) + 0x20
        padlen = pad_up(base + imglen_with_digest, 0x4000)
        imglen_with_padding = imglen_with_digest + padlen
        # fix next_img
        sub[4:8] = imglen_with_padding.to_bytes(4, "little")
        sub += b"\xAA" * 32
        sub += b"\x87" * padlen
        base += len(sub)

    # ota_signature
    buf[0:32] = mac(hash_key, sub_imgs[0][:LEN_HDR_IMG])

    for i, (sub, sig_offset) in enumerate(zip(sub_imgs, sig_offsets)):
        print(f"{i=} {sig_offset=:#x}")
        raw = (buf + sub[:sig_offset]) if i == 0 else sub[:sig_offset]
        sub[sig_offset : sig_offset + 32] = mac(hash_key, raw)
        buf += sub

    return bytes(buf)


def from_elf(elf: ELFFile, serial: int, hash_key: bytes, pubkeys: list[bytes] | None = None) -> bytes:
    ram_img = SubImage(
        type=ImageType.FWHS_S,
        serial=serial,
        sections=[],
    )
    xip_imgs = []

    entry = elf["e_entry"]

    for seg in elf.iter_segments("PT_LOAD"):
        seg_addr = seg["p_vaddr"]
        seg_end = seg_addr + seg["p_memsz"]
        data = seg.data()

        if not data:
            continue

        if seg_addr & 0xfff0_0000 == 0x1000_0000:
            # RAM
            ram_img.sections.append(
                Section(
                    type=SectionType.SRAM,
                    section_base=seg_addr,
                    data=seg.data(),
                )
            )
        elif seg_addr & 0xff00_0000 == 0x9b00_0000:
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
            LOG.warning("ignoring segment in unknown address space: 0x%08x", seg_addr)

    # assumption: the bootloader expects the entry point on the first ram image's
    # section, not the one that actually contains the address
    # (will most likely coincide anyways)
    ram_img.sections[0].entry_point = elf["e_entry"]

    img = Image([ram_img] + xip_imgs, pubkeys=pubkeys or [])

    for sub in img.subs:
        LOG.info("sub image %s", sub.type)
        for sect in sub.sections:
            LOG.info("  section 0x%08x (entry = 0x%08x): %s", sect.section_base, sect.entry_point, sect.type)

    return build(hash_key, img)


def main() -> None:
    logging.basicConfig(
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s", level=logging.DEBUG
    )

    parser = argparse.ArgumentParser()
    parser.add_argument("elf", type=ELFFile.load_from_path)
    parser.add_argument("output", type=argparse.FileType("wb"))
    parser.add_argument("--serial", type=int)
    parser.add_argument("--hash-key-hex", type=bytes.fromhex, dest="hash_key")

    args = parser.parse_args()

    with args.elf:
        firmware = from_elf(args.elf, args.serial, args.hash_key, [])

    with args.output:
        args.output.write(firmware)


if __name__ == "__main__":
    main()

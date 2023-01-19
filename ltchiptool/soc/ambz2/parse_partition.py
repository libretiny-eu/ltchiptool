# Copyright 2022 Kjell Braden
# licensed under MIT License

from enum import IntEnum

import typer
from construct import *
from Cryptodome.Hash import HMAC, SHA256

ptable_pattern = bytes.fromhex("999996963FCC66FCC033CC03E5DC3162")
padding = b"\xff" * 16
assert len(ptable_pattern) == 16


default_hash_key = bytes.fromhex(
    "47E5661335A4C5E0A94D69F3C737D54F2383791332939753EF24279608F6D72B"
)

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


class PartitionType(IntEnum):
    PARTAB = 0
    BOOT = 1
    SYS = 2
    CAL = 3
    USER = 4
    FW1 = 5
    FW2 = 6
    VAR = 7
    MP = 8
    RDP = 9
    UNKNOWN = 10


class SectionType(IntEnum):
    UNSET = 0x00
    DTCM = 0x80
    ITCM = 0x81
    SRAM = 0x82
    PSRAM = 0x83
    LPDDR = 0x84
    XIP = 0x85
    UNKNOWN = 0xFF


HDR = Struct(
    "segment_size" / Hex(Int32ul),
    "next_img" / Hex(Int32ul),
    "type" / Enum(Byte, ImageType),
    "is_encrypted" / Hex(Byte),
    "is_partab_or_boot"
    / Rebuild(Byte, lambda ctx: 0xFF if ctx.type in ("PARTAB", "BOOT") else 0),
    "flags" / FlagsEnum(Byte, key1_set=1, key2_set=2),
    "unused_0" / Hex(Bytes(8)),
    "serial" / Hex(Int32ul),
    "unused_1" / Hex(Bytes(8)),
    "user_key1" / Hex(Bytes(32)),
    "user_key2" / Hex(Bytes(32)),
)
assert HDR.sizeof() == 0x60

PartRec = Struct(
    "start_address" / Hex(Int32ul),
    "length" / Hex(Int32ul),
    "type" / Enum(Byte, PartitionType),
    "dbg_skip" / Hex(Byte),
    "reserved_0" / Hex(Bytes(6)),
    "key_valid" / FlagsEnum(Byte, hash=1),
    "reserved_1" / Hex(Bytes(15)),
    "hash_key" / Hex(Bytes(32)),
)
assert PartRec.sizeof() == 0x40

PT_Payload = Struct(
    "rma_w_state" / Hex(Byte),
    "rma_ov_state" / Hex(Byte),
    "eFWV" / Hex(Byte),
    "res_0" / Hex(Byte),
    "num_imgs" / Hex(Byte),
    "fw1_idx" / Hex(Byte),
    "fw2_idx" / Hex(Byte),
    "res_1" / Hex(Bytes(3)),
    "ota_trap" / Hex(Int16ul),
    "mp_trap" / Hex(Int16ul),
    "res_2" / Hex(Bytes(1)),
    "key_exp_op" / Hex(Byte),
    "user_data_len" / Hex(Int16ul),
    "user_ext" / Hex(Bytes(14)),
    "boot_record" / PartRec,
    "part_records" / PartRec[this.num_imgs],
    "user_data" / HexDump(Bytes(this.user_data_len)),
)

PT = Struct(
    "pattern" / Const(ptable_pattern),
    Padding(16, pattern=b"\xff"),
    "dec_pubkey" / Hex(Bytes(32)),
    "hash_pubkey" / Hex(Bytes(32)),
    "hdr" / HDR,
    "data" / FixedSized(this.hdr.segment_size, PT_Payload),
    "hash" / Hex(Bytes(32)),
)

EntryHeader = Aligned(
    32,
    Struct(
        "len" / Hex(Int32ul),
        "section_base" / Hex(Int32ul),
        "entry_address" / Hex(Int32ul),
    ),
)

BootImg = Struct(
    "dec_pubkey" / Hex(Bytes(32)),
    "hash_pubkey" / Hex(Bytes(32)),
    "hdr" / HDR,
    "entry_hdr" / EntryHeader,
    "image_start" / Hex(Tell),
    "image" / Bytes(this.hdr.segment_size - 0x20),
    "hash" / Hex(Bytes(32)),
)


FST = Struct(
    "enc_algo" / Hex(Int16ul),
    "hash_algo" / Hex(Int16ul),
    "part_size" / Hex(Int32ul),
    "valid_pattern" / Hex(Bytes(8)),
    Padding(4),
    "flags" / FlagsEnum(Byte, encrypted=1, hashed=2),
    "key_valid" / FlagsEnum(Byte, cipher=1),
    Padding(10),
    "cipher_key" / Hex(Bytes(32)),
    "cipher_iv" / Hex(Bytes(16)),
    Padding(0x10),
)
assert FST.sizeof() == (0x50 + 0x10), FST.sizeof()


Section = Struct(
    "size" / Hex(Int32ul),
    "next_section_header" / Hex(Int32ul),
    "type" / Enum(Byte, SectionType),
    # SCE == secure code engine, for XIP decryption
    "sce_enable" / Hex(Byte),
    "xip_page_size" / Hex(Byte),
    "xip_block_size" / Hex(Byte),
    Padding(4),
    "valid_pattern" / Hex(Bytes(8)),
    "flags" / FlagsEnum(Byte, has_xip_key_iv=1),
    Padding(7),
    "xip_key" / Hex(Bytes(16)),
    "xip_iv" / Hex(Bytes(16)),
    Padding(32),
    "entry_hdr" / EntryHeader,
    "image_start" / Hex(Tell),
    "image" / Aligned(0x20, Bytes(this.size - 0x20)),
)


SubImg_Payload = Struct(
    "fst" / FST,
    "sections"
    / RepeatUntil(
        lambda obj, lst, ctx: obj.next_section_header == 0xFFFFFFFF,
        Section,
    ),
)


SubImg = Struct(
    "_start" / Hex(Tell),
    "hdr" / HDR,
    "data" / If(this.hdr.segment_size != 0xFFFFFFFF, SubImg_Payload),
    # XXX disabled FixedSized because it messes with Tell, breaking image_start
    # "data" / If(this.hdr.segment_size != 0xFFFFFFFF, FixedSized(this.hdr.segment_size, SubImg_Payload)),
    "hash" / Hex(Bytes(32)),
    If(this.hdr.next_img != 0xFFFFFFFF, Seek(this._start + this.hdr.next_img)),
)

FWImg = Struct(
    "ota_signature" / Hex(Bytes(32)),
    "pubkey" / Hex(Bytes(32))[6],
    "sub_imgs"
    / RepeatUntil(
        lambda obj, lst, ctx: obj.hdr.next_img == 0xFFFFFFFF,
        SubImg,
    ),
)


def parse_fw(file: typer.FileBinaryRead, hash_key: bytes = None) -> None:
    offset = file.tell()
    parsed_fw = FWImg.parse_stream(file)

    print(f"\n{parsed_fw}")

    if parsed_fw.ota_signature == b"\xff" * 32:
        return

    if hash_key:
        if parsed_fw.ota_signature != MARKER_UNSIGNED:
            file.seek(offset + 32 * 7)
            digest = mac(hash_key, file.read(0x60))
            if digest != parsed_fw.ota_signature:
                print(f"ota_signature MISMATCH: computed={digest.hex()}")

        for img_idx, img in enumerate(parsed_fw.sub_imgs):
            if img.data is None:
                return
            if not img.data.fst.flags.hashed:
                return

            hash_start = offset if img_idx == 0 else img._start
            file.seek(hash_start)

            off = img._start - hash_start
            raw = file.read(HDR.sizeof() + img.hdr.segment_size + off)
            digest = mac(hash_key, raw)

            if digest != img.hash:
                print(
                    f"""\
    {img_idx=} {file.tell()=:#x} {len(raw)=}
    MISMATCH: computed={digest.hex()}"""
                )


def main(file: typer.FileBinaryRead, fw: bool = False, hash_key_hex: str = None):
    if fw:
        parse_fw(file, bytes.fromhex(hash_key_hex) if hash_key_hex else None)
        return

    parsed_pt = PT.parse_stream(file)
    print(f"{parsed_pt}")
    print(f"{file.tell()=:#x}")

    assert parsed_pt.hdr.segment_size % 0x20 == 0
    file.seek(0x20)
    raw_pt = file.read(0x40 + 0x60 + parsed_pt.hdr.segment_size)
    pt_digest = mac(default_hash_key, raw_pt)
    if pt_digest != parsed_pt.hash:
        print(
            f"""\
{file.tell()=:#x} {len(raw_pt)=}
MISMATCH: computed={pt_digest.hex()}"""
        )

    file.seek(parsed_pt.data.boot_record.start_address)
    parsed_bootimg = BootImg.parse_stream(file)
    print()
    print(f"{parsed_bootimg}")
    print(f"{file.tell()=:#x}")

    file.seek(parsed_pt.data.boot_record.start_address)
    raw_bootimg = file.read(0x20 + 0x20 + 0x60 + parsed_bootimg.hdr.segment_size)
    bootimg_digest = mac(default_hash_key, raw_bootimg)
    if bootimg_digest != parsed_bootimg.hash:
        print(
            f"""\
{file.tell()=:#x} {len(raw_bootimg)=}
MISMATCH: computed={bootimg_digest.hex()}"""
        )

    for part_idx, rec in enumerate(parsed_pt.data.part_records):
        file.seek(rec.start_address)

        print(f"\n# {part_idx+1}")
        parse_fw(file, rec.hash_key if rec.key_valid.hash else None)


if __name__ == "__main__":
    typer.run(main)

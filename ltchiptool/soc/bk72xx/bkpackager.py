# Copyright (c) Kuba Szczodrzyński 2022-07-29.

import sys
from os.path import dirname, join

sys.path.append(join(dirname(__file__), "..", "..", ".."))

from argparse import ArgumentParser, FileType
from io import SEEK_SET, FileIO
from os import stat
from time import time
from typing import Union

from util import RBL, BekenBinary

from ltchiptool.util.intbin import ByteGenerator, fileiter


def auto_int(x):
    return int(x, 0)


def add_common_args(parser):
    parser.add_argument(
        "coeffs", type=str, help="Encryption coefficients (hex string, 32 chars)"
    )
    parser.add_argument("input", type=FileType("rb"), help="Input file")
    parser.add_argument("output", type=FileType("wb"), help="Output file")
    parser.add_argument("addr", type=auto_int, help="Memory address (dec/hex)")


if __name__ == "__main__":
    parser = ArgumentParser(description="Encrypt/decrypt Beken firmware binaries")
    sub = parser.add_subparsers(dest="action", required=True)

    encrypt = sub.add_parser("encrypt", help="Encrypt binary files without packaging")
    add_common_args(encrypt)
    encrypt.add_argument("-c", "--crc", help="Include CRC16", action="store_true")

    decrypt = sub.add_parser("decrypt", description="Decrypt unpackaged binary files")
    add_common_args(decrypt)
    decrypt.add_argument(
        "-C",
        "--no-crc-check",
        help="Do not check CRC16 (if present)",
        action="store_true",
    )

    package = sub.add_parser(
        "package", description="Package raw binary files as RBL containers"
    )
    add_common_args(package)
    package.add_argument(
        "size", type=auto_int, help="RBL total size (excl. CRC) (dec/hex)"
    )
    package.add_argument(
        "-n",
        "--name",
        type=str,
        help="Firmware name (default: app)",
        default="app",
        required=False,
    )
    package.add_argument(
        "-v",
        "--version",
        type=str,
        help="Firmware version (default: 1.00)",
        default="1.00",
        required=False,
    )

    unpackage = sub.add_parser(
        "unpackage", description="Unpackage a single RBL container"
    )
    add_common_args(unpackage)
    unpackage.add_argument(
        "offset", type=auto_int, help="Offset in input file (dec/hex)"
    )
    unpackage.add_argument(
        "size", type=auto_int, help="Container total size (incl. CRC) (dec/hex)"
    )

    args = parser.parse_args()
    bk = BekenBinary(args.coeffs)
    f: FileIO = args.input
    size = stat(args.input.name).st_size
    start = time()
    gen: Union[ByteGenerator, None] = None

    if args.action == "encrypt":
        print(f"Encrypting '{f.name}' ({size} bytes)")
        if args.crc:
            print(f" - calculating 32-byte block CRC16...")
            gen = bk.crc(bk.crypt(args.addr, f))
        else:
            print(f" - as raw binary, without CRC16...")
            gen = bk.crypt(args.addr, f)

    if args.action == "decrypt":
        print(f"Decrypting '{f.name}' ({size} bytes)")
        if size % 34 == 0:
            if args.no_crc_check:
                print(f" - has CRC16, skipping checks...")
            else:
                print(f" - has CRC16, checking...")
            gen = bk.crypt(args.addr, bk.uncrc(f, check=not args.no_crc_check))
        elif size % 4 != 0:
            raise ValueError("Input file has invalid length")
        else:
            print(f" - raw binary, no CRC")
            gen = bk.crypt(args.addr, f)

    if args.action == "package":
        print(f"Packaging {args.name} '{f.name}' for memory address 0x{args.addr:X}")
        rbl = RBL(name=args.name, version=args.version)
        if args.name == "bootloader":
            rbl.has_part_table = True
            print(f" - in bootloader mode; partition table unencrypted")
        rbl.container_size = args.size
        print(f" - container size (excl. CRC): 0x{rbl.container_size:X}")
        print(f" - container size (incl. CRC): 0x{rbl.container_size_crc:X}")
        gen = bk.package(f, args.addr, size, rbl)

    if args.action == "unpackage":
        print(f"Unpackaging '{f.name}' (at 0x{args.offset:X}, size 0x{args.size:X})")
        f.seek(args.offset + args.size - 102, SEEK_SET)
        rbl = f.read(102)
        rbl = b"".join(bk.uncrc(rbl))
        rbl = RBL.deserialize(rbl)
        print(f" - found '{rbl.name}' ({rbl.version}), size {rbl.data_size}")
        f.seek(0, SEEK_SET)
        crc_size = (rbl.data_size - 16) // 32 * 34
        gen = bk.crypt(args.addr, bk.uncrc(fileiter(f, 32, 0xFF, crc_size)))

    if not gen:
        raise RuntimeError("gen is None")

    written = 0
    for data in gen:
        args.output.write(data)
        written += len(data)
    print(f" - wrote {written} bytes in {time()-start:.3f} s")

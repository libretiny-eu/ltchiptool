# Copyright (c) Kuba Szczodrzyński 2022-07-29.

from datetime import datetime
from io import SEEK_SET, BytesIO
from os import stat
from os.path import basename
from typing import Dict, Optional

from ltchiptool import Board
from ltchiptool.util import chext, chname, isnewer, str2enum
from ltchiptool.util.intbin import inttobe32, pad_data

from .util import RBL, BekenBinary, DataType, OTACompression, OTAEncryption


def calc_offset(addr: int) -> int:
    return int(addr + (addr // 32) * 2)


def elf2bin(board: Board, input: str, ota_idx: int) -> Dict[str, Optional[int]]:
    toolchain = board.toolchain
    result: Dict[str, Optional[int]] = {}

    mcu = board["build.mcu"]
    coeffs = board["build.bkcrypt_coeffs"] or ("0" * 32)
    rbl_size = board["build.bkrbl_size_app"]
    ota_encryption = board["build.bkota.encryption"]
    ota_compression = board["build.bkota.compression"]
    ota_key = board["build.bkota.key"]
    ota_iv = board["build.bkota.iv"]
    _, ota_size, _ = board.region("download")
    version = datetime.now().strftime("%y.%m.%d")

    nmap = toolchain.nm(input)
    app_addr = nmap["_vector_start"]
    app_offs = calc_offset(app_addr)
    app_size = int(rbl_size, 16)
    rbl_offs = app_offs + int(app_size // 32 * 34) - 102

    # build output names
    out_rbl = chname(input, f"{mcu}_app_0x{app_offs:06X}.rbl")
    out_crc = chname(input, f"{mcu}_app_0x{app_offs:06X}.crc")
    out_rblh = chname(input, f"{mcu}_app_0x{rbl_offs:06X}.rblh")
    out_ota = chname(input, f"{mcu}_app.ota.rbl")
    out_ug = chname(input, f"{mcu}_app.ota.ug.bin")
    fw_bin = chext(input, "bin")
    outputs = [out_rbl, out_crc, out_rblh, out_ota, out_ug]
    # print graph element
    print(f"|   |-- {basename(out_rbl)}")
    # objcopy ELF -> raw BIN
    toolchain.objcopy(input, fw_bin)
    result[fw_bin] = None
    # return if all outputs are up-to-date
    if all(map(lambda f: isnewer(f, fw_bin), outputs)):
        result[out_rbl] = app_offs
        result[out_crc] = None
        result[out_rblh] = rbl_offs
        result[out_ota] = None
        result[out_ug] = None
        return result

    bk = BekenBinary(coeffs)
    rbl = RBL(
        name="app",
        version=f"{version}-{mcu}",
        container_size=app_size,
    )

    fw_size = stat(fw_bin).st_size
    raw = open(fw_bin, "rb")
    out = open(out_rbl, "wb")

    # open encrypted+CRC binary output
    print(f"|   |-- {basename(out_crc)}")
    crc = open(out_crc, "wb")

    # get partial (type, bytes) data generator
    package_gen = bk.package(raw, app_addr, fw_size, rbl, partial=True)

    # write all BINARY blocks
    for data_type, data in package_gen:
        if data_type != DataType.BINARY:
            break
        out.write(data)
        crc.write(data)

    # skip PADDING_SIZE bytes for RBL header, write it to main output
    if data_type == DataType.PADDING_SIZE:
        out.write(b"\xff" * data)

    # open RBL header output
    print(f"|   |-- {basename(out_rblh)}")
    rblh = open(out_rblh, "wb")

    # write all RBL blocks
    for data_type, data in package_gen:
        if data_type != DataType.RBL:
            break
        out.write(data)
        rblh.write(data)

    result[out_rbl] = app_offs
    result[out_crc] = None
    result[out_rblh] = rbl_offs

    # write OTA package
    rbl = RBL(
        name="app",
        version=f"{version}-{mcu}",
        encryption=str2enum(OTAEncryption, ota_encryption) or OTAEncryption.NONE,
        compression=str2enum(OTACompression, ota_compression) or OTACompression.NONE,
    )
    print(f"|   |-- {basename(out_ota)}")
    # seek back to start
    raw.seek(0, SEEK_SET)
    ota_gen = bk.ota_package(raw, rbl, key=ota_key, iv=ota_iv)
    ota_data = BytesIO()
    ota = open(out_ota, "wb")
    for data in ota_gen:
        ota.write(data)
        ota_data.write(data)
    if rbl.data_size > ota_size:
        print(f"OTA size too large: {rbl.data_size} > {ota_size} (0x{ota_size:X})")
    result[out_ota] = None

    # write Tuya OTA package (UG)
    print(f"|   |-- {basename(out_ug)}")
    with open(out_ug, "wb") as ug:
        hdr = BytesIO()
        ota_bin = ota_data.getvalue()
        hdr.write(b"\x55\xAA\x55\xAA")
        hdr.write(pad_data(version.encode(), 12, 0x00))
        hdr.write(inttobe32(len(ota_bin)))
        hdr.write(inttobe32(sum(ota_bin)))
        ug.write(hdr.getvalue())
        ug.write(inttobe32(sum(hdr.getvalue())))
        ug.write(b"\xAA\x55\xAA\x55")
        ug.write(ota_bin)
    result[out_ug] = None

    # close all files
    raw.close()
    out.close()
    crc.close()
    rblh.close()
    ota.close()
    return result

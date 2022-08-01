# Copyright (c) Kuba Szczodrzyński 2022-07-29.

from datetime import datetime
from io import SEEK_SET
from os import stat
from os.path import basename
from typing import Dict, Optional

from ltchiptool.models import Board
from ltchiptool.util import chext, chname, isnewer, str2enum

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
    rbl_offs = app_offs

    # build output name
    output = chname(input, f"{mcu}_app_0x{app_offs:06X}.rbl")
    fw_bin = chext(input, "bin")
    # print graph element
    print(f"|   |-- {basename(output)}")
    # objcopy ELF -> raw BIN
    toolchain.objcopy(input, fw_bin)
    result[fw_bin] = None
    # return if images are up to date
    if not isnewer(fw_bin, output):
        result[output] = app_offs
        return result

    bk = BekenBinary(coeffs)
    rbl = RBL(
        name="app",
        version=f"{version}-{mcu}",
        container_size=app_size,
    )

    fw_size = stat(fw_bin).st_size
    raw = open(fw_bin, "rb")
    out = open(output, "wb")

    # open encrypted+CRC binary output
    out_crc = chname(input, f"{mcu}_app_0x{app_offs:06X}.crc")
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
        rbl_offs += len(data)

    # skip PADDING_SIZE bytes for RBL header, write it to main output
    if data_type == DataType.PADDING_SIZE:
        out.write(b"\xff" * data)
        rbl_offs += data

    # open RBL header output
    out_rblh = chname(input, f"{mcu}_app_0x{rbl_offs:06X}.rblh")
    print(f"|   |-- {basename(out_rblh)}")
    rblh = open(out_rblh, "wb")

    # write all RBL blocks
    for data_type, data in package_gen:
        if data_type != DataType.RBL:
            break
        out.write(data)
        rblh.write(data)

    result[output] = app_offs
    result[out_crc] = None
    result[out_rblh] = rbl_offs

    # write OTA package
    rbl = RBL(
        name="app",
        version=f"{version}-{mcu}",
        encryption=str2enum(OTAEncryption, ota_encryption) or OTAEncryption.NONE,
        compression=str2enum(OTACompression, ota_compression) or OTACompression.NONE,
    )
    out_ota = chname(input, f"{mcu}_app_ota.rbl")
    print(f"|   |-- {basename(out_ota)}")
    # seek back to start
    raw.seek(0, SEEK_SET)
    ota_gen = bk.ota_package(raw, rbl, key=ota_key, iv=ota_iv)
    ota = open(out_ota, "wb")
    for data in ota_gen:
        ota.write(data)
    if rbl.data_size > ota_size:
        print(f"OTA size too large: {rbl.data_size} > {ota_size} (0x{ota_size:X})")

    # close all files
    raw.close()
    out.close()
    crc.close()
    rblh.close()
    ota.close()
    return result

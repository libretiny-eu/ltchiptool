# Copyright (c) Kuba Szczodrzyński 2022-07-29.

from abc import ABC
from datetime import datetime
from io import SEEK_SET, BytesIO, FileIO
from logging import warning
from os import stat
from os.path import basename
from typing import Dict, Optional, Tuple, Union

from ltchiptool import SocInterface
from ltchiptool.util import CRC16, chext, chname, graph, isnewer, peek, str2enum
from ltchiptool.util.intbin import betoint, gen2bytes, inttobe32, pad_data

from .util import RBL, BekenBinary, DataType, OTACompression, OTAEncryption


def calc_offset(addr: int) -> int:
    return int(addr + (addr // 32) * 2)


def check_app_code_crc(data: bytes) -> Union[bool, None]:
    # b #0x40
    # ldr pc, [pc, #0x14]
    if data[0:8] == b"\x2F\x07\xB5\x94\x35\xFF\x2A\x9B":
        crc = CRC16.CMS.calc(data[0:32])
        crc_found = betoint(data[32:34])
        if crc == crc_found:
            return True
        warning("File CRC16 invalid. Considering as non-CRC file.")
        return
    return None


class BK72XXBinary(SocInterface, ABC):
    def elf2bin(self, input: str, ota_idx: int) -> Dict[str, Optional[int]]:
        toolchain = self.board.toolchain
        result: Dict[str, Optional[int]] = {}

        mcu = self.board["build.mcu"]
        coeffs = self.board["build.bkcrypt_coeffs"] or ("0" * 32)
        rbl_size = self.board["build.bkrbl_size_app"]
        ota_encryption = self.board["build.bkota.encryption"]
        ota_compression = self.board["build.bkota.compression"]
        ota_key = self.board["build.bkota.key"]
        ota_iv = self.board["build.bkota.iv"]
        _, ota_size, _ = self.board.region("download")
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
        graph(1, basename(out_rbl))
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
        graph(1, basename(out_crc))
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
        graph(1, basename(out_rblh))
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
            compression=str2enum(OTACompression, ota_compression)
            or OTACompression.NONE,
        )
        graph(1, basename(out_ota))
        # seek back to start
        raw.seek(0, SEEK_SET)
        ota_gen = bk.ota_package(raw, rbl, key=ota_key, iv=ota_iv)
        ota_data = BytesIO()
        ota = open(out_ota, "wb")
        for data in ota_gen:
            ota.write(data)
            ota_data.write(data)
        if rbl.data_size > ota_size:
            warning(
                f"OTA size too large: {rbl.data_size} > {ota_size} (0x{ota_size:X})"
            )
        result[out_ota] = None

        # write Tuya OTA package (UG)
        graph(1, basename(out_ug))
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

    def detect_file_type(
        self,
        file: FileIO,
        length: int,
    ) -> Optional[Tuple[str, Optional[int], int, int]]:
        data = peek(file, size=96)
        if not data:
            return None
        bk = BekenBinary()

        # app firmware file - opcodes encrypted for 0x10000
        app_code = check_app_code_crc(data)
        if app_code is None:
            pass
        elif app_code:
            return "Beken CRC App", 0x11000, 0, min(length, 0x121000)
        elif not app_code:
            return "Beken Encrypted App", None, 0, 0

        # raw firmware binary
        if data[0:8] == b"\x0E\x00\x00\xEA\x14\xF0\x9F\xE5":
            return "Raw ARM Binary", None, 0, 0

        # RBL file for OTA - 'download' partition
        try:
            rbl = RBL.deserialize(data)
            if rbl.encryption or rbl.compression:
                return "Beken OTA", None, 0, 0
        except ValueError:
            # no OTA RBL - continue checking
            pass

        # tried all known non-CRC formats - make sure CRC is okay
        try:
            bk.uncrc(data[0 : 34 * 2], check=True)
        except ValueError:
            # invalid CRC - nothing more to do
            return None

        # CRC is okay, but it's not app file - try to find bootloader RBL
        # read RBL+CRC and app opcodes
        data = peek(file, size=34 * 4, seek=0x10F9A)
        if not data:
            return None

        # file with bootloader - possibly a full dump
        try:
            rbl_data = gen2bytes(bk.uncrc(data[0 : 34 * 3], check=True))
            rbl = RBL.deserialize(rbl_data)
            if rbl.encryption or rbl.compression:
                return None
        except ValueError:
            # no bootloader RBL - give up
            return None

        # full dump file - encrypted app opcodes at 0x11000
        app_code = check_app_code_crc(data[34 * 3 : 34 * 4])
        if app_code:
            blocks = length // 1024
            if blocks == 2048:
                name = "Beken Full Dump"
            elif blocks == 1192:
                name = "Beken BL+APP Dump"
            else:
                name = "Beken Incomplete Dump"
            return name, 0x11000, 0x11000, min(length - 0x11000, 0x121000)

        return None

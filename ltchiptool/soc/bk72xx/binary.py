# Copyright (c) Kuba Szczodrzyński 2022-07-29.

from abc import ABC
from datetime import datetime
from io import SEEK_SET, BytesIO
from logging import warning
from os import stat
from typing import IO, List, Optional, Union

from ltchiptool import SocInterface
from ltchiptool.util.crc16 import CRC16
from ltchiptool.util.detection import Detection
from ltchiptool.util.fileio import chext, peek
from ltchiptool.util.fwbinary import FirmwareBinary
from ltchiptool.util.intbin import betoint, gen2bytes, inttobe32, pad_data
from ltchiptool.util.obj import str2enum

from .util import RBL, BekenBinary, DataType, OTACompression, OTAEncryption


def to_offset(addr: int) -> int:
    return int(addr + (addr // 32) * 2)


def to_address(offs: int) -> int:
    return int(offs - (offs // 34) * 2)


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
    def elf2bin(self, input: str, ota_idx: int) -> List[FirmwareBinary]:
        toolchain = self.board.toolchain

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
        app_offs = to_offset(app_addr)
        app_size = int(rbl_size, 16)
        rbl_offs = app_offs + to_offset(app_size) - 102

        app_part_offs = self.board.region("app")[0]
        if app_offs != app_part_offs:
            raise ValueError(
                f"App partition offset (0x{app_part_offs:06X}) doesn't match "
                f"the generated binary offset (0x{app_offs:06X})"
            )

        # build output names
        out_ug = FirmwareBinary(
            location=input,
            name=f"{mcu}_app",
            subname="ota.ug",
            ext="bin",
            title="Cloudcutter Image",
            description="UG Image for flashing with tuya-cloudcutter",
            public=True,
        )
        out_ota = FirmwareBinary(
            location=input,
            name=f"{mcu}_app",
            subname="ota",
            ext="rbl",
            title="Beken OTA Image",
            description="For flashing using Beken or OpenBeken OTA",
            public=True,
        )
        out_rbl = FirmwareBinary(
            location=input,
            name=f"{mcu}_app",
            offset=app_offs,
            ext="rbl",
            title="Beken Application Image",
            public=True,
        )
        out_crc = FirmwareBinary(
            location=input,
            name=f"{mcu}_app",
            offset=app_offs,
            ext="crc",
            title="Beken CRC/UA App",
        )
        out_rblh = FirmwareBinary(
            location=input,
            name=f"{mcu}_app",
            offset=rbl_offs,
            ext="rblh",
            title="Beken Application RBL Header",
        )
        fw_bin = chext(input, "bin")
        # print graph element
        out_rbl.graph(1)
        # objcopy ELF -> raw BIN
        toolchain.objcopy(input, fw_bin)
        # return if all outputs are up-to-date
        if all(binary.isnewer(than=fw_bin) for binary in out_rbl.group_get()):
            return out_rbl.group()

        bk = BekenBinary(coeffs)
        rbl = RBL(
            name="app",
            version=f"{version}-{mcu}",
            container_size=app_size,
        )

        fw_size = stat(fw_bin).st_size
        raw = open(fw_bin, "rb")
        out = out_rbl.write()

        # open encrypted+CRC binary output
        out_crc.graph(1)
        crc = out_crc.write()

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
        out_rblh.graph(1)
        rblh = out_rblh.write()

        # write all RBL blocks
        for data_type, data in package_gen:
            if data_type != DataType.RBL:
                break
            out.write(data)
            rblh.write(data)

        # write OTA package
        rbl = RBL(
            name="app",
            version=f"{version}-{mcu}",
            encryption=str2enum(OTAEncryption, ota_encryption) or OTAEncryption.NONE,
            compression=str2enum(OTACompression, ota_compression)
            or OTACompression.NONE,
        )
        out_ota.graph(1)
        # seek back to start
        raw.seek(0, SEEK_SET)
        ota_gen = bk.ota_package(raw, rbl, key=ota_key, iv=ota_iv)
        ota_data = BytesIO()
        ota = out_ota.write()
        for data in ota_gen:
            ota.write(data)
            ota_data.write(data)
        if rbl.data_size > ota_size:
            warning(
                f"OTA size too large: {rbl.data_size} > {ota_size} (0x{ota_size:X})"
            )

        # write Tuya OTA package (UG)
        out_ug.graph(1)
        with out_ug.write() as ug:
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

        # close all files
        raw.close()
        out.close()
        crc.close()
        rblh.close()
        ota.close()
        return out_rbl.group()

    def detect_file_type(
        self,
        file: IO[bytes],
        length: int,
    ) -> Optional[Detection]:
        data = peek(file, size=96)
        if not data:
            return None
        bk = BekenBinary()

        # app firmware file - opcodes encrypted for 0x10000
        app_code = check_app_code_crc(data)
        if app_code is True:
            return Detection.make("Beken CRC/UA App", 0x11000, 0, min(length, 0x121000))
        if app_code is False:
            return Detection.make_unsupported("Beken Encrypted App")

        # raw firmware binary
        if data[0:8] == b"\x0E\x00\x00\xEA\x14\xF0\x9F\xE5":
            return Detection.make_unsupported("Raw ARM Binary")

        # RBL file for OTA - 'download' partition
        try:
            rbl = RBL.deserialize(data)
            if rbl.encryption or rbl.compression:
                return Detection.make("Beken OTA", 0x132000, 0, length)
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
        data = peek(file, size=34 * 4, seek=to_offset(0x10000 - 0x60))
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
            if length == to_offset(0x10000 + 0x108700):
                name = "Beken QIO Firmware"
            elif length == 0x100000:
                name = "Beken QIO (OBK T) Firmware"
            elif blocks == 2048:
                name = "Beken Full Dump"
            elif blocks == 1192:
                name = "Beken BL+APP Dump"
            else:
                name = "Beken Incomplete Dump"
            length = min(length - 0x11000, 0x121000)
            return Detection.make(name, 0x11000, 0x11000, length)

        return None

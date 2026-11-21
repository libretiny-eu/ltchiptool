# Copyright (c) Kuba Szczodrzyński 2022-07-29.

from abc import ABC
from datetime import datetime
from io import SEEK_SET, BytesIO
from logging import warning
from os import stat, unlink
from typing import IO, List, Optional, Union

from ltchiptool import SocInterface
from ltchiptool.util.crc16 import CRC16
from ltchiptool.util.detection import Detection
from ltchiptool.util.fileio import chext, peek
from ltchiptool.util.fwbinary import FirmwareBinary
from ltchiptool.util.intbin import betoint, gen2bytes, inttobe32, pad_data
from ltchiptool.util.obj import str2enum

from .util import (
    RBL,
    BekenBinary,
    DataType,
    OTACompression,
    OTAEncryption,
    diff2ya_package,
    diff2ya_package_info,
)

# XIP base address of the flash memory on BK7236 (beken-72xx-gen2)
GEN2_FLASH_BASE = 0x02000000


def to_offset(addr: int) -> int:
    return int(addr + (addr // 32) * 2)


def to_address(offs: int) -> int:
    return int(offs - (offs // 34) * 2)


def check_app_code_crc(data: bytes) -> Union[bool, None]:
    # b #0x40
    # ldr pc, [pc, #0x14]
    if data[0:8] == b"\x2f\x07\xb5\x94\x35\xff\x2a\x9b":
        crc = CRC16(CRC16.CMS).calc(data[0:32])
        crc_found = betoint(data[32:34])
        if crc == crc_found:
            return True
        warning("File CRC16 invalid. Considering as non-CRC file.")
        return
    return None


class BK72XXBinary(SocInterface, ABC):
    def elf2bin(self, input: str, ota_idx: int) -> List[FirmwareBinary]:
        if self.family.is_child_of("beken-72xx-gen2"):
            return self.elf2bin_gen2(input)

        toolchain = self.board.toolchain

        mcu = self.board["build.mcu"]
        coeffs = self.board["build.bkcrypt_coeffs"] or ("0" * 32)
        rbl_size = self.board["build.bkrbl_size_app"]
        ota_encryption = self.board["build.bkota.encryption"]
        ota_compression = self.board["build.bkota.compression"]
        ota_key = self.board["build.bkota.key"]
        ota_iv = self.board["build.bkota.iv"]
        ota_format = self.board["build.bkota.format"]
        ota_offs, ota_size, _ = self.board.region("download")
        version = datetime.now().strftime("%y.%m.%d")

        # Fallback for LibreTiny v1.12.x and older
        if not ota_format:
            ota_format = "rbl-ug"

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
            title="Cloudcutter Image (UG)",
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
        out_d2info = FirmwareBinary(
            location=input,
            name=f"{mcu}_app",
            subname="diff2ya",
            ext="dat",
            title="Tuya T1 OTA info",
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

        # write Beken OTA package
        ota_data = BytesIO()
        if ota_format in ["rbl", "rbl-ug"]:
            rbl = RBL(
                name="app",
                version=f"{version}-{mcu}",
                encryption=str2enum(OTAEncryption, ota_encryption)
                or OTAEncryption.NONE,
                compression=str2enum(OTACompression, ota_compression)
                or OTACompression.NONE,
            )
            out_ota.graph(1)
            # seek back to start
            raw.seek(0, SEEK_SET)
            ota_gen = bk.ota_package(raw, rbl, key=ota_key, iv=ota_iv)
            with out_ota.write() as ota:
                for data in ota_gen:
                    ota.write(data)
                    ota_data.write(data)
            if rbl.data_size > ota_size:
                warning(
                    f"OTA size too large: {rbl.data_size} > {ota_size} (0x{ota_size:X})"
                )

        # write Tuya OTA package (UG)
        if ota_format == "rbl-ug":
            out_ug.graph(1)
            with out_ug.write() as ug:
                hdr = BytesIO()
                ota_bin = ota_data.getvalue()
                hdr.write(b"\x55\xaa\x55\xaa")
                hdr.write(pad_data(version.encode(), 12, 0x00))
                hdr.write(inttobe32(len(ota_bin)))
                hdr.write(inttobe32(sum(ota_bin)))
                ug.write(hdr.getvalue())
                ug.write(inttobe32(sum(hdr.getvalue())))
                ug.write(b"\xaa\x55\xaa\x55")
                ug.write(ota_bin)

        # write diff2ya OTA package (UG)
        if ota_format == "diff2ya":
            out_ug.graph(1)
            with out_ug.write() as ug:
                raw.seek(0, SEEK_SET)
                d2a_gen = diff2ya_package(raw)
                ota_len = 0
                for data in d2a_gen:
                    ug.write(data)
                    ota_len += len(data)
                # write the diff2ya "manage info" partition
                d2i_data = diff2ya_package_info(ota_offs, ota_len)
                out_d2info.graph(2)
                with out_d2info.write() as d2i:
                    d2i.write(d2i_data)

        # close all files
        raw.close()
        out.close()
        crc.close()
        rblh.close()
        return out_rbl.group()

    def elf2bin_gen2(self, input: str) -> List[FirmwareBinary]:
        toolchain = self.board.toolchain
        mcu = self.board["build.mcu"]

        nmap = toolchain.nm(input)
        if "__vector_table" not in nmap:
            raise ValueError("Symbol '__vector_table' not found in the ELF file")
        app_addr = nmap["__vector_table"] - GEN2_FLASH_BASE
        app_offs = to_offset(app_addr)
        app_part_offs, app_part_size, _ = self.board.region("app")
        if app_offs != app_part_offs:
            raise ValueError(
                f"App partition offset (0x{app_part_offs:06X}) doesn't match "
                f"the generated binary offset (0x{app_offs:06X})"
            )

        # build output names
        out_crc = FirmwareBinary(
            location=input,
            name=f"{mcu}_app",
            offset=app_offs,
            ext="crc",
            title="Beken CRC App",
            description="For flashing to the app partition",
            public=True,
        )
        # Tuya diff2ya OTA package (used by the BK7236 bootloader)
        ota_format = self.board["build.bkota.format"]
        if ota_format not in (None, "diff2ya"):
            raise ValueError(f"OTA format '{ota_format}' is not supported on {mcu}")
        if ota_format == "diff2ya":
            ota_offs, ota_size, _ = self.board.region("download")
            if not self.board["build.bkota.flh_len"]:
                raise ValueError("diff2ya OTA needs 'build.bkota.flh_len' in the board")
            flh_len = int(self.board["build.bkota.flh_len"], 16)
            d2i_offs, _, _ = self.board.region("diff2ya")
            out_ug = FirmwareBinary(
                location=input,
                name=f"{mcu}_app",
                subname="ota.ug",
                ext="bin",
                title="Tuya diff2ya OTA Image",
                description="For flashing using OTA",
                public=True,
            )
            out_d2info = FirmwareBinary(
                location=input,
                name=f"{mcu}_app",
                subname="diff2ya",
                ext="dat",
                title="Tuya diff2ya OTA info",
            )
        fw_bin = chext(input, "bin")
        # print graph element
        out_crc.graph(1)
        # objcopy ELF -> raw BIN
        toolchain.objcopy(input, fw_bin)
        # return if all outputs are up-to-date
        if all(binary.isnewer(than=fw_bin) for binary in out_crc.group_get()):
            return out_crc.group()

        # the app image is not encrypted, only CRC16 is added every 32 bytes
        bk = BekenBinary()
        with open(fw_bin, "rb") as raw, out_crc.write() as crc:
            for block in bk.crc(raw):
                crc.write(block)

        crc_size = stat(out_crc.path).st_size
        if crc_size > app_part_size:
            # remove it, so that the next build doesn't consider it up-to-date
            unlink(out_crc.path)
            raise ValueError(
                f"App image too large: {crc_size} > {app_part_size} "
                f"(0x{app_part_size:X})"
            )

        # write diff2ya OTA package (UG) and its "manage info" partition
        if ota_format == "diff2ya":
            out_ug.graph(1)
            ota_len = 0
            with open(fw_bin, "rb") as raw, out_ug.write() as ug:
                for data in diff2ya_package(raw):
                    ug.write(data)
                    ota_len += len(data)
            if ota_len > ota_size:
                unlink(out_ug.path)
                unlink(out_crc.path)
                raise ValueError(
                    f"OTA image too large: {ota_len} > {ota_size} (0x{ota_size:X})"
                )
            out_d2info.graph(2)
            with out_d2info.write() as d2i:
                d2i.write(
                    diff2ya_package_info(
                        ota_offs,
                        ota_len,
                        flh_len,
                        # second manage info block, erased by the bootloader anyway
                        backup_offs=d2i_offs + 0x1000,
                    )
                )
        return out_crc.group()

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
        if data[0:8] == b"\x0e\x00\x00\xea\x14\xf0\x9f\xe5":
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

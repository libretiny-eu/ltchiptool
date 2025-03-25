#!/usr/bin/env python3
# -*- coding:utf-8 -*-
#
# Copyright 2021 Shanghai Lightning Semiconductor Technology Co., LTD

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# fmt: off
# isort:skip_file

import argparse
import json

from .models.boot_header import *
from .models.image_header import *
from .models.part_desc_info import *


class MakeImageTool:
    def __init__(self) -> None:
        self.__boot_filepath        = None
        self.__app_filepath         = None
        self.__flashimage_filepath  = None
        self.__part_cfg_filepath    = None
        self.__ver_str              = None
        self.__ver_major            = 0
        self.__ver_minor            = 0
        self.__swd_crp              = 0
        self.__verbose              = 0

        self.__part_desc_info_list  = []
        self.__partbuf_bootram      = None
        self.__partbuf_parttab      = None
        self.__partbuf_nvds         = None
        self.__partbuf_app          = None
        self.__partbuf_kv           = None
        self.__partbuf_eeprom       = None

    def readPartCfg(self) -> bool:
        try:
            with open(self.part_cfg_filepath, "r", encoding="utf-8") as fObj:
                root_node = json.load(fp=fObj)
                vendor_node = root_node["vendor_define"]
                user_node = root_node["user_define"]

                for node in vendor_node:
                    parttype = part_type_str2num(node["partition_type"])
                    startaddr = int(node["start_addr"], 16)
                    partsize = node["size_KB"] * 1024

                    part_info = PartDescInfo(parttype=parttype, startaddr=startaddr, partsize=partsize)
                    self.__part_desc_info_list.append(part_info)

                for node in user_node:
                    parttype = part_type_str2num(node["partition_type"])
                    startaddr = int(node["start_addr"], 16)
                    partsize = node["size_KB"] * 1024

                    part_info = PartDescInfo(parttype=parttype, startaddr=startaddr, partsize=partsize)
                    self.__part_desc_info_list.append(part_info)

        except Exception as err:
            print("Error: open partition cfg file failed: {}".format(str(err)))
            return False

        if len(self.__part_desc_info_list) >= 4:
            print("----------" * 10)
            for item in self.__part_desc_info_list:
                print(item)
            print("----------" * 10)

            return True

        return False

    def genPartBufPartTab(self) -> bool:
        parttab_part = self.getPartDescInfoFromList(PART_TYPE_PART_TAB)
        if not parttab_part:
            print("Error: partition table has not been found!!!")
            return False

        part_tab_buffer = bytearray(parttab_part.part_size)
        part_tab_buffer = part_tab_buffer.replace(b'\x00', b'\xFF')

        offset = 0
        for part in self.__part_desc_info_list:
            if isinstance(part, PartDescInfo):
                if (part.part_type == PART_TYPE_BOOT) or (part.part_type == PART_TYPE_PART_TAB) or (part.part_type == PART_TYPE_INVALID):
                    continue
                part_tab_buffer[offset:(offset+PARTITION_DESC_INFO_SIZE)] = part.toBytes()
                offset += PARTITION_DESC_INFO_SIZE

        part_tab_buffer[offset:(offset+PARTITION_DESC_INFO_SIZE)] = bytearray(PARTITION_DESC_INFO_SIZE)[:]

        self.__partbuf_parttab = part_tab_buffer
        return True

    def getPartDescInfoFromList(self, part_type) -> PartDescInfo:
        if not isinstance(part_type, int):
            raise TypeError("Error: part_type MUST be an int value!!!")

        for part_info in self.__part_desc_info_list:
            if isinstance(part_info, PartDescInfo):
                if part_info.part_type == part_type:
                    return part_info
        return None

    def checkFileSize(self) -> bool:
        boot_fileinfo = os.stat(self.boot_filepath)
        app_fileinfo = os.stat(self.app_filepath)

        max_boot_filesize = self.getPartDescInfoFromList(PART_TYPE_BOOT).part_size
        max_app_filesize = self.getPartDescInfoFromList(PART_TYPE_APP).part_size

        if boot_fileinfo.st_size >= max_boot_filesize:
            print("FAIL -- checking {}".format(self.boot_filepath))
            return False
        print("PASS -- checking {}".format(self.boot_filepath))

        if app_fileinfo.st_size >= max_app_filesize:
            print("FAIL -- checking {}".format(self.app_filepath))
            return False
        print("PASS -- checking {}".format(self.app_filepath))


        return True

    def genPartBufBootRam(self) -> bool:
        boot_part = self.getPartDescInfoFromList(PART_TYPE_BOOT)
        if not boot_part:
            print("Error: BOOT partition has not been found!!!")
            return False

        bootram_buffer = bytearray(boot_part.part_size)
        bootram_buffer = bootram_buffer.replace(b'\x00', b'\xFF')

        fileInfo = os.stat(self.boot_filepath)
        try:
            with open(self.boot_filepath, "rb") as fObj:
                bootram_content = fObj.read()
                bootheader = BootHeader(bootram_content)
                if self.swd_crp == 0:
                    bootheader.crp_flag = 0
                else:
                    bootheader.crp_flag = BootHeader.CRP_VALID_FLAG

                bootram_buffer[0:BootHeader.BOOT_HEADER_SIZE] = bootheader.toByteArray()[:]
                bootram_buffer[BootHeader.BOOT_HEADER_SIZE:fileInfo.st_size] = bootram_content[BootHeader.BOOT_HEADER_SIZE:fileInfo.st_size]
                self.__partbuf_bootram = bootram_buffer

        except Exception as err:
            print("Error: open boot file failed: {}".format(str(err)))
            return False

        return True

    def genPartBufKV(self) -> bool:
        kv_part = self.getPartDescInfoFromList(PART_TYPE_KV)
        if kv_part:
            kv_buffer = bytearray(kv_part.part_size)
            kv_buffer = kv_buffer.replace(b'\x00', b'\xFF')
            self.__partbuf_kv = kv_buffer
        return True

    def genPartBufEEPROM(self) -> bool:
        eeprom_part = self.getPartDescInfoFromList(PART_TYPE_SIMU_EEPROM)
        if eeprom_part:
            eeprom_buffer = bytearray(eeprom_part.part_size)
            eeprom_buffer = eeprom_buffer.replace(b'\x00', b'\xFF')
            self.__partbuf_eeprom = eeprom_buffer
        return True

    def genPartBufAPP(self) -> bool:
        app_part = self.getPartDescInfoFromList(PART_TYPE_APP)
        if not app_part:
            print("Error: APP part is not found in the partition table!!!")
            return False

        try:
            with open(self.app_filepath, "rb") as fObj:
                app_content = fObj.read()

                image_header = ImageHeader(bytearray(256))
                image_header.image_type = IMAGE_TYPE_ORIGINAL
                image_header.setVerMajor(self.__ver_major)
                image_header.setVerMinor(self.__ver_minor)
                image_header.img_size_orig = len(app_content)
                image_header.img_crc32_orig = zlib.crc32(app_content)

                temp = bytearray(image_header.toBytes())
                temp.extend(app_content)
                self.__partbuf_app = temp
        except Exception as err:
            print("Error: open app file failed: {}".format(str(err)))
            return False

        if not self.__partbuf_app:
            return False

        return True

    def writeOutputFile(self) -> bool:
        if not self.__partbuf_bootram:
            print("Error: ramcode has not been processed!!!")
            return False

        if not self.__partbuf_parttab:
            print("Error: partition table has not been processed!!!")
            return False

        if not self.__partbuf_nvds:
            nvds_part = self.getPartDescInfoFromList(PART_TYPE_NVDS)
            if nvds_part:
                nvds_buffer = bytearray(nvds_part.part_size)
                nvds_buffer = nvds_buffer.replace(b'\x00', b'\xFF')
                self.__partbuf_nvds = nvds_buffer

        if not self.__partbuf_app:
            print("Error: app has not been processed!!!")
            return False

        if not self.__partbuf_kv:
            print("Error: KV has not been processed!!!")
            return False

        try:
            with open(self.flashimage_filepath, "wb") as fObj:
                # ram code
                ramcode_part = self.getPartDescInfoFromList(PART_TYPE_BOOT)
                fObj.seek(ramcode_part.start_addr, os.SEEK_SET)
                fObj.write(self.__partbuf_bootram)

                # partition table
                parttab_part = self.getPartDescInfoFromList(PART_TYPE_PART_TAB)
                fObj.seek(parttab_part.start_addr, os.SEEK_SET)
                fObj.write(self.__partbuf_parttab)

                # APP
                app_part = self.getPartDescInfoFromList(PART_TYPE_APP)
                fObj.seek(app_part.start_addr, os.SEEK_SET)
                fObj.write(self.__partbuf_app)

                # NVDS
                nvds_part = self.getPartDescInfoFromList(PART_TYPE_NVDS)
                if (not nvds_part) and nvds_part.start_addr < app_part.start_addr:
                    fObj.seek(nvds_part.start_addr, os.SEEK_SET)
                    fObj.write(self.__partbuf_nvds)

                # KV
                kv_part = self.getPartDescInfoFromList(PART_TYPE_KV)
                if kv_part.start_addr < app_part.start_addr:
                    fObj.seek(kv_part.start_addr, os.SEEK_SET)
                    fObj.write(self.__partbuf_kv)

                # SIMU_EEPROM
                eeprom_part = self.getPartDescInfoFromList(PART_TYPE_SIMU_EEPROM)
                if eeprom_part and (eeprom_part.start_addr < app_part.start_addr):
                    fObj.seek(eeprom_part.start_addr, os.SEEK_SET)
                    fObj.write(self.__partbuf_eeprom)
        except Exception as err:
            print("Error: open file failed: {}!!!".format(str(err)))
            return False

        return True

    def doAllWork(self) -> bool:
        if not self.readPartCfg():
            return False

        if not self.genPartBufPartTab():
            return False

        if not self.checkFileSize():
            print("Error: file size check failed!!!")
            return False

        if not self.genPartBufBootRam():
            print("Error: ram code wrong!!!")
            return False

        if not self.genPartBufKV():
            print("Error: KV wrong!!!")
            return False

        if not self.genPartBufEEPROM():
            print("Error: EEPROM wrong!!!")
            return False

        if not self.genPartBufAPP():
            print("Error: process app content!!!")
            return False

        if not self.writeOutputFile():
            print("Error: final store!!!")
            return False

        return True

    @property
    def boot_filepath(self):
        return self.__boot_filepath

    @boot_filepath.setter
    def boot_filepath(self, boot):
        if isinstance(boot, str):
            if os.path.exists(boot):
                self.__boot_filepath = boot
            else:
                raise ValueError("Error: not exist: {} !!!".format(boot))
        else:
            raise TypeError("Error: boot MUST be a str!!!")

    @property
    def app_filepath(self):
        return self.__app_filepath

    @app_filepath.setter
    def app_filepath(self, app):
        if isinstance(app, str):
            if os.path.exists(app):
                self.__app_filepath = app
            else:
                raise ValueError("Error: not exist: {} !!!".format(app))
        else:
            raise TypeError("Error: app MUST be a str!!!")

    @property
    def flashimage_filepath(self):
        return self.__flashimage_filepath

    @flashimage_filepath.setter
    def flashimage_filepath(self, flashimage):
        if isinstance(flashimage, str):
            dest_dir = os.path.dirname(flashimage)
            if os.path.exists(dest_dir):
                self.__flashimage_filepath = flashimage
            else:
                raise ValueError("Error: directory for {} NOT exist!!!".format(flashimage))
        else:
            raise TypeError("Error: flashimage MUST be a str!!!")

    @property
    def part_cfg_filepath(self):
        return self.__part_cfg_filepath

    @part_cfg_filepath.setter
    def part_cfg_filepath(self, part_cfg):
        if isinstance(part_cfg, str):
            if os.path.exists(part_cfg):
                self.__part_cfg_filepath = part_cfg
            else:
                raise ValueError("Error: not exist: {}".format(part_cfg))
        else:
            raise TypeError("Error: part_cfg MUST be a str!!!")

    @property
    def ver_str(self):
        return self.__ver_str

    @ver_str.setter
    def ver_str(self, ver):
        """
        `ver` is a str with format "<major>.<minor>", such as "1.2" or "2.3".
        """
        if isinstance(ver, str):
            temp_list = ver.split(".")
            if (len(temp_list) == 2) and temp_list[0].isnumeric() and temp_list[1].isnumeric():
                self.__ver_str = ver
                self.__ver_major = int(temp_list[0])
                self.__ver_minor = int(temp_list[1])
            else:
                raise ValueError("Error: ver MUST be like '1.2' (major.minor)")
        else:
            raise TypeError("Error: ver MUST be a str!!!")

    @property
    def verbose(self):
        return self.__verbose

    @verbose.setter
    def verbose(self, verbose):
        if isinstance(verbose, int):
            self.__verbose = verbose % 3
        else:
            raise TypeError("Error: verbose MUST be [0, 1, 2]")

    @property
    def swd_crp(self) -> int:
        return self.__swd_crp

    @swd_crp.setter
    def swd_crp(self, crp):
        if isinstance(crp, int):
            if crp == 0:
                self.__swd_crp = 0
            else:
                self.__swd_crp = 1
        else:
            raise TypeError("Error: crp MUST be one of [0, 1]!!!")

    def __str__(self):
        output_str = (  "\n------  mkimage  ------\n" \
                        "2nd boot: {_boot}\n"   \
                        "app.bin : {_app}\n"    \
                        "output  : {_flash}\n"  \
                        "part_cfg: {_part}\n"   \
                        "ver str : {_ver}\n"    \
                        .format(_boot=self.boot_filepath, _app=self.app_filepath,
                                _flash=self.flashimage_filepath, _part=self.part_cfg_filepath, _ver=self.ver_str))
        return output_str


if __name__ == "__main__":
    """
    The following arguments are required:
    --boot      /path/to/boot_ln88xx.bin, that is ramcode;
    --app       /path/to/app.bin, that is compiler output;
    --output    /path/to/flashimage.bin, that is our final image file which can be downloaded to flash;
    --part      /path/to/flash_partition_cfg.json, that is configuration for flash partition;
    --ver       APP version, like "1.2", but is only used for LN SDK boot, not for user app version;

    The following arguments are optional:
    --crp       which change the SWD behavior, 0 -- SWD protect is disabled; 1 -- SWD protect is enabled;

    Usage
    =====
    python3  makeimage.py  -h
    """
    prog = os.path.basename(__file__)
    desc = "makeimage tool for LN88XX"
    parser = argparse.ArgumentParser(prog=prog, description=desc)
    parser.add_argument("--boot",   help="/path/to/boot_ln88xx.bin", type=str)
    parser.add_argument("--app",    help="/path/to/app.bin", type=str)
    parser.add_argument("--output", help="/path/to/flashimage.bin, that is output filepath", type=str)
    parser.add_argument("--part",   help="/path/to/flash_partition_cfg.json", type=str)
    parser.add_argument("--ver",    help="APP version (only used for LN SDK boot), such as 1.2", type=str)
    parser.add_argument("--crp",    help="SWD protect bit [0 -- disable, 1 -- enable]", type=int, choices=[0, 1])

    args = parser.parse_args()

    if args.boot is None:
        print("Error: /path/to/boot_ln88xx.bin has not been set!!!")
        exit(-1)

    if args.app is None:
        print("Error: /path/to/app.bin has not been set!!!")
        exit(-2)

    if args.output is None:
        print("Error: /path/to/flashimage.bin has not been set!!!")
        exit(-3)

    if args.part is None:
        print("Error: /path/to/flash_partition_cfg.json has not been set!!!")
        exit(-4)

    if args.ver is None:
        print("Error: LN SDK boot version has not been set!!!")
        exit(-5)

    mkimage = MakeImageTool()
    mkimage.boot_filepath       = args.boot
    mkimage.app_filepath        = args.app
    mkimage.flashimage_filepath = args.output
    mkimage.part_cfg_filepath   = args.part
    mkimage.ver_str             = args.ver

    if args.crp:
        mkimage.swd_crp         = args.crp

    if not mkimage.doAllWork():
        exit(-1)

    exit(0)

#  Copyright (c) 2026 bavci1988.

import struct
from abc import ABC
from os.path import isfile
from typing import IO, List, Optional

from ltchiptool import SocInterface
from ltchiptool.util.detection import Detection
from ltchiptool.util.fileio import chext, chname, peek
from ltchiptool.util.fwbinary import FirmwareBinary

from .util.awih import (
    ID_APP,
    ID_APP_XIP,
    ID_BOOT,
    ID_SYS_SDD,
    ID_WLAN_BL,
    ID_WLAN_FW,
    Layout,
    Section,
    make_image,
    make_ota_image,
)

AWIH_MAGIC = b"AWIH"
SECTION_ID_BOOT = 0xA5FF5A00
SECTION_ID_APP = 0xA5FE5A01


# load and entry addresses of the SDK (config.mk), without TrustZone
BOOT_SRAM = 0x00230000
APP_SRAM = 0x00201000


class XR806Binary(SocInterface, ABC):
    def elf2bin(self, input: str, ota_idx: int) -> List[FirmwareBinary]:
        toolchain = self.board.toolchain

        # SDK binaries, copied next to the ELF by the builder
        def read_sdk_bin(name: str) -> bytes:
            path = chname(input, name)
            if not isfile(path):
                raise FileNotFoundError(f"SDK image part not found: {path}")
            with open(path, "rb") as f:
                return f.read()

        output = FirmwareBinary(
            location=input,
            name="firmware",
            ext="img",
            offset=0,
            title="Flash Image",
            description="Complete image with bootloader for flashing at offset 0",
            public=True,
        )
        out_boot = FirmwareBinary(
            location=input,
            name="boot",
            offset=self.board.region("boot")[0],
            title="Bootloader Image",
        )
        out_app = FirmwareBinary(
            location=input,
            name="app",
            offset=self.board.region("app")[0],
            title="Application Image",
            description="Firmware partition image for direct flashing",
            public=True,
        )
        out_ota = FirmwareBinary(
            location=input,
            name="ota",
            offset=self.board.region("download")[0],
            title="OTA Image",
            description="Compressed application image for OTA flashing",
            public=True,
        )
        # print graph element
        output.graph(1)

        # the .xip section runs from flash, everything else is loaded into RAM
        input_ram = chext(input, "bin")
        input_xip = chname(input, "app_xip.bin")
        toolchain.cmd(
            "objcopy", ["-O", "binary", "-R", ".xip", input, input_ram]
        ).read()
        toolchain.objcopy(input, input_xip, sections=[".xip"])
        with open(input_ram, "rb") as f:
            app_ram = f.read()
        with open(input_xip, "rb") as f:
            app_xip = f.read()

        boot_offset, boot_size, _ = self.board.region("boot")
        app_offset, app_size, app_end = self.board.region("app")
        ota_cfg_offset, ota_cfg_size, _ = self.board.region("ota_cfg")
        _, download_size, _ = self.board.region("download")
        flash_size = int(self.board["upload.flash_size"])
        layout = Layout(
            app_offset=app_offset,
            ota_cfg_offset=ota_cfg_offset,
            ota_cfg_size=ota_cfg_size,
            image_limit=app_end,
            xz_slot_size=download_size,
        )
        sections = [
            Section(
                ID_BOOT, read_sdk_bin("boot.bin"), 0x1, BOOT_SRAM, BOOT_SRAM + 0x101
            ),
            Section(ID_APP, app_ram, 0x1, APP_SRAM, APP_SRAM + 0x101),
            Section(ID_APP_XIP, app_xip, 0x2),
            Section(ID_WLAN_BL, read_sdk_bin("wlan_bl.bin"), 0x1),
            Section(ID_WLAN_FW, read_sdk_bin("wlan_fw.bin"), 0x1),
            Section(ID_SYS_SDD, read_sdk_bin("sys_sdd.bin"), 0x1),
        ]
        image = make_image(sections, layout, flash_size)

        with output.write() as f:
            f.write(image)
        with out_boot.write() as f:
            f.write(image[boot_offset : boot_offset + boot_size])
        with out_app.write() as f:
            f.write(image[app_offset:])
        with out_ota.write() as f:
            f.write(make_ota_image(image, flash_size))
        return output.group()

    def detect_file_type(
        self,
        file: IO[bytes],
        length: int,
    ) -> Optional[Detection]:
        data = peek(file, size=64)
        if not data or data[0:4] != AWIH_MAGIC:
            return None
        section_id = struct.unpack_from("<I", data, 0x24)[0]
        # xr_system.img from the SDK starts with the bootloader section
        if section_id == SECTION_ID_BOOT:
            return Detection.make("XR806 System Image", offset=0)
        return Detection.make_unsupported("XR806 Section Image")

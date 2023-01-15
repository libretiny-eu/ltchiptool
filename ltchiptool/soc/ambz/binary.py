# Copyright (c) Kuba Szczodrzyński 2022-07-29.

from abc import ABC
from os.path import basename
from struct import unpack
from typing import IO, Dict, Optional, Tuple

from ltchiptool import SocInterface
from ltchiptool.util.detection import Detection
from ltchiptool.util.fileio import chname, isnewer, peek, readbin
from ltchiptool.util.intbin import inttole32
from ltchiptool.util.logging import graph


def write_header(f: IO[bytes], start: int, end: int):
    f.write(b"81958711")
    f.write(inttole32(end - start))
    f.write(inttole32(start))
    f.write(b"\xff" * 16)


def check_xip_binary(
    data: bytes,
    header: bytes = b"81958711",
) -> Optional[Tuple[int, int, bytes]]:
    if data[0:8] != header:
        return None
    if data[16:32] != b"\xFF" * 16:
        return None
    length, start = unpack("<II", data[8:16])
    return start, length, data[32:]


def check_bootloader_binary(data: bytes) -> Optional[Tuple[int, int, bytes]]:
    return check_xip_binary(data, header=b"\x99\x99\x96\x96\x3F\xCC\x66\xFC")


class AmebaZBinary(SocInterface, ABC):
    def elf2bin(
        self,
        input: str,
        ota_idx: int,
    ) -> Dict[str, Optional[int]]:
        toolchain = self.board.toolchain
        result: Dict[str, Optional[int]] = {}

        sections_ram = [
            ".ram_image2.entry",
            ".ram_image2.data",
            ".ram_image2.bss",
            ".ram_image2.skb.bss",
            ".ram_heap.data",
        ]
        sections_xip = [".xip_image2.text"]
        sections_rdp = [".ram_rdp.text"]
        nmap = toolchain.nm(input)
        ram_start = nmap["__ram_image2_text_start__"]
        ram_end = nmap["__ram_image2_text_end__"]
        xip_start = nmap["__flash_text_start__"] - 0x8000020
        # build output name
        output = chname(input, f"image_0x{xip_start:06X}.ota{ota_idx}.bin")
        out_ram = chname(input, f"ota{ota_idx}.ram_2.r.bin")
        out_xip = chname(input, f"ota{ota_idx}.xip_image2.bin")
        out_rdp = chname(input, f"ota{ota_idx}.rdp.bin")
        # print graph element
        graph(1, basename(output))
        # objcopy required images
        ram = toolchain.objcopy(input, out_ram, sections_ram)
        xip = toolchain.objcopy(input, out_xip, sections_xip)
        toolchain.objcopy(input, out_rdp, sections_rdp)
        # add to outputs
        result[out_ram] = None
        result[out_xip] = None
        result[out_rdp] = None
        # return if images are up-to-date
        if not isnewer(ram, output) and not isnewer(xip, output):
            result[output] = xip_start
            return result

        # read and trim RAM image
        ram = readbin(ram).rstrip(b"\x00")
        # read XIP image
        xip = readbin(xip)
        # align images to 4 bytes
        ram += b"\x00" * (((((len(ram) - 1) // 4) + 1) * 4) - len(ram))
        xip += b"\x00" * (((((len(xip) - 1) // 4) + 1) * 4) - len(xip))
        # write output file
        with open(output, "wb") as f:
            # write XIP header
            write_header(f, 0, len(xip))
            # write XIP image
            f.write(xip)
            # write RAM header
            write_header(f, ram_start, ram_end)
            # write RAM image
            f.write(ram)
        result[output] = xip_start
        return result

    def detect_file_type(
        self,
        file: IO[bytes],
        length: int,
    ) -> Optional[Detection]:
        data = peek(file, size=64)
        if not data:
            return None

        if data[0x08:0x0E] == b"RTKWin" or data[0x28:0x2E] == b"RTKWin":
            return Detection.make_unsupported("Realtek AmebaZ RAM Image")

        # stage 0 - check XIP file
        tpl = check_xip_binary(data)
        if tpl:
            start, xip_length, data = tpl
            start = start or None
            type = "SDK" if data.startswith(b"Customer") else "LT"
            if start:
                if start & 0x8000020 != 0x8000020:
                    return Detection.make_unsupported("Realtek AmebaZ Unknown Image")
                ota_idx = 1 if start == 0x800B020 else 2
                return Detection.make(
                    type_name=f"Realtek AmebaZ {type}-XIP{ota_idx}",
                    offset=start & ~0x8000020,
                    skip=0,
                    length=xip_length,
                )
            return Detection.make(f"Realtek AmebaZ {type}-XIP Unknown", offset=None)

        # stage 1 - check Realtek OTA 1+2 file
        if data[0x08:0x0C] == b"OTA1" and data[0x20:0x24] == b"OTA2":
            if data[0x38:0x40] != b"81958711":
                return Detection.make_unsupported("Realtek OTA Package Invalid")
            xip_length, skip, start = unpack("<III", data[0x14:0x20])
            return Detection.make(
                type_name=f"Realtek OTA Package",
                offset=start & ~0x8000020,
                skip=skip,
                length=xip_length,
            )

        # stage 2 - check full dump file
        tpl = check_bootloader_binary(data)
        if not tpl:
            # no bootloader at 0x0, nothing to do
            return None
        start, xip_length, _ = tpl
        if start & 0x8000020 != 0x8000020:
            # make sure the bootloader offset is correct
            return None
        # read app header
        data = peek(file, size=64, seek=0xB000)
        if not data:
            # bootloader only binary
            if xip_length >= 0x4000:
                # too long, probably not AmebaZ
                return None
            return Detection.make(
                type_name="Realtek AmebaZ Bootloader",
                offset=start & ~0x8000020,
                skip=0,
                length=xip_length,
            )
        # check XIP at 0xB000
        tpl = check_xip_binary(data)
        if not tpl:
            return None

        if length != 2048 * 1024:
            return Detection.make("Realtek AmebaZ Incomplete Dump", offset=None)
        return Detection.make("Realtek AmebaZ Full Dump", 0, 0, 0)

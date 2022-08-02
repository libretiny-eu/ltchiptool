# Copyright (c) Kuba Szczodrzyński 2022-07-29.

from os.path import basename
from typing import IO, Dict, Optional

from ltchiptool import Board
from ltchiptool.util import chname, isnewer, readbin
from ltchiptool.util.intbin import inttole32


def write_header(f: IO[bytes], start: int, end: int):
    f.write(b"81958711")
    f.write(inttole32(end - start))
    f.write(inttole32(start))
    f.write(b"\xff" * 16)


def elf2bin(board: Board, input: str, ota_idx: int) -> Dict[str, Optional[int]]:
    toolchain = board.toolchain
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
    print(f"|   |-- {basename(output)}")
    # objcopy required images
    ram = toolchain.objcopy(input, out_ram, sections_ram)
    xip = toolchain.objcopy(input, out_xip, sections_xip)
    toolchain.objcopy(input, out_rdp, sections_rdp)
    # add to outputs
    result[out_ram] = None
    result[out_xip] = None
    result[out_rdp] = None
    # return if images are up to date
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

# Copyright (c) Kuba Szczodrzyński 2022-07-29.

from os.path import basename
from subprocess import PIPE, Popen
from typing import IO, Dict, List

from .fileio import isnewer
from .logging import graph


class Toolchain:
    def __init__(self, prefix: str):
        self.prefix = prefix

    def cmd(self, program: str, args: List[str] = None) -> IO[bytes]:
        if not args:
            args = []
        program = self.prefix + program
        cmd = [program] + args
        try:
            process = Popen(cmd, stdout=PIPE)
        except FileNotFoundError:
            if isinstance(cmd, list):
                cmd = " ".join(cmd)
            raise FileNotFoundError(f"Toolchain not found while running: '{cmd}'")
        return process.stdout

    def nm(self, input: str) -> Dict[str, int]:
        out = {}
        stdout = self.cmd("gcc-nm", [input])
        for line in stdout.readlines():
            line = line.decode().strip().split(" ")
            if len(line) != 3:
                continue
            out[line[2]] = int(line[0], 16)
        return out

    def objcopy(
        self,
        input: str,
        output: str,
        sections: List[str] = None,
        fmt: str = "binary",
    ) -> str:
        if not sections:
            sections = []
        # print graph element
        graph(2, basename(output))
        if isnewer(input, output):
            args = []
            for section in sections:
                args += ["-j", section]
            args += ["-O", fmt]
            args += [input, output]
            self.cmd("objcopy", args).read()
        return output

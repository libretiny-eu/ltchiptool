# Copyright (c) Kuba Szczodrzyński 2022-05-27.

import click


class Input:
    ota1_part: str = None
    ota1_offs: int = 0
    ota1_file: str = None
    ota2_part: str = None
    ota2_offs: int = 0
    ota2_file: str = None

    def __init__(self, input: str) -> None:
        input = input.split(";")
        n = len(input)
        if n not in [2, 4]:
            raise ValueError(
                "Incorrect input format - should be part+offs;file[;part+offs;file]"
            )
        # just spread the same image twice for single-OTA scheme
        if n == 2:
            input += input

        if input[0] and input[1]:
            if "+" in input[0]:
                (self.ota1_part, ota1_offs) = input[0].split("+")
                self.ota1_offs = int(ota1_offs, 0)
            else:
                self.ota1_part = input[0]
            self.ota1_file = input[1]
        if input[2] and input[3]:
            if "+" in input[2]:
                (self.ota2_part, ota2_offs) = input[2].split("+")
                self.ota2_offs = int(ota2_offs, 0)
            else:
                self.ota2_part = input[2]
            self.ota2_file = input[3]

        if self.ota1_file and self.ota2_file and self.ota1_offs != self.ota2_offs:
            # currently, offsets cannot differ when storing images
            # (this would require to actually store it twice)
            raise ValueError(f"Offsets cannot differ ({self.ota1_file})")

    @property
    def is_single(self) -> bool:
        return self.ota1_part == self.ota2_part and self.ota1_file == self.ota2_file

    @property
    def single_part(self) -> str:
        return self.ota1_part or self.ota2_part

    @property
    def single_offs(self) -> int:
        return self.ota1_offs or self.ota2_offs

    @property
    def single_file(self) -> str:
        return self.ota1_file or self.ota2_file

    @property
    def has_ota1(self) -> bool:
        return not not (self.ota1_part and self.ota1_file)

    @property
    def has_ota2(self) -> bool:
        return not not (self.ota2_part and self.ota2_file)

    @property
    def is_simple(self) -> bool:
        return self.ota1_file == self.ota2_file or not (self.has_ota1 and self.has_ota2)


class InputParamType(click.ParamType):
    name = "input"

    def convert(self, value, param, ctx) -> Input:
        try:
            return Input(value)
        except ValueError as e:
            self.fail(e.args[0], param, ctx)

# Copyright (c) Kuba Szczodrzyński 2022-06-02.

from os.path import isdir, join
from typing import List, Union

import click

from ltchiptool.util import lt_find_path, lt_read_json

LT_FAMILIES: List["Family"] = []


class Family:
    id: int
    short_name: str
    description: str
    name: str = None
    parent: str = None
    code: str = None
    parent_code: str = None
    url: str = None
    sdk: str = None
    framework: str = None
    mcus: List[str] = []

    def __init__(self, data: dict):
        for key, value in data.items():
            if key == "id":
                self.id = int(value, 16)
            else:
                setattr(self, key, value)

    @classmethod
    def get_all(cls) -> List["Family"]:
        global LT_FAMILIES
        if LT_FAMILIES:
            return LT_FAMILIES
        LT_FAMILIES = [cls(f) for f in lt_read_json("families.json")]
        return LT_FAMILIES

    @classmethod
    def get(
        cls,
        any: str = None,
        id: Union[str, int] = None,
        short_name: str = None,
        name: str = None,
        code: str = None,
    ) -> "Family":
        if any:
            id = any
            short_name = any
            name = any
            code = any
        if id and isinstance(id, str) and id.startswith("0x"):
            id = int(id, 16)
        for family in cls.get_all():
            if id and family.id == id:
                return family
            if short_name and family.short_name == short_name.upper():
                return family
            if name and family.name == name.lower():
                return family
            if code and family.code == code.lower():
                return family
        if any:
            raise ValueError(f"Family not found - {any}")
        text = ", ".join(filter(None, [id, short_name, name, code]))
        raise ValueError(f"Family not found - {text}")

    @property
    def sdk_name(self) -> str:
        return self.sdk.rpartition("/")[2] if self.sdk else None

    @property
    def has_arduino_core(self) -> bool:
        if not self.name:
            return False
        if isdir(join(lt_find_path(), "arduino", self.name)):
            return True
        if not self.parent:
            return False
        if isdir(join(lt_find_path(), "arduino", self.parent)):
            return True
        return False

    def dict(self) -> dict:
        return dict(
            FAMILY=self.short_name,
            FAMILY_ID=self.id,
            FAMILY_NAME=self.name,
            FAMILY_PARENT=self.parent,
            FAMILY_CODE=self.code,
            FAMILY_PARENT_CODE=self.parent_code,
        )

    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, Family) and self.id == __o.id

    def __iter__(self):
        return iter(self.dict().items())

    def __repr__(self) -> str:
        return f"<Family: {self.short_name}(0x{self.id:X}), name={self.name}, parent={self.parent}>"


class FamilyParamType(click.ParamType):
    name = "family"

    def convert(self, value, param, ctx) -> Family:
        try:
            return Family.get(value)
        except FileNotFoundError:
            self.fail(f"Family {value} does not exist", param, ctx)

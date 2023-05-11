# Copyright (c) Kuba Szczodrzyński 2022-06-02.

from dataclasses import dataclass, field
from os.path import isdir, join
from typing import List, Optional, Union

import click

from ltchiptool.util.lvm import LVM

LT_FAMILIES: List["Family"] = []


@dataclass
class Family:
    name: str
    parent: Union["Family", None]
    code: str
    description: str
    id: Optional[int] = None
    short_name: Optional[str] = None
    package: Optional[str] = None
    mcus: List[str] = field(default_factory=lambda: [])
    children: List["Family"] = field(default_factory=lambda: [])

    # noinspection PyTypeChecker
    def __post_init__(self):
        if self.id:
            self.id = int(self.id, 16)
        self.mcus = set(self.mcus)

    @classmethod
    def get_all(cls) -> List["Family"]:
        global LT_FAMILIES
        if LT_FAMILIES:
            return LT_FAMILIES
        families = LVM.get().load_json("families.json", version=True)
        LT_FAMILIES = [
            cls(name=k, **v) for k, v in families.items() if isinstance(v, dict)
        ]
        # attach parents and children to all families
        for family in LT_FAMILIES:
            if family.parent is None:
                continue
            try:
                parent = next(f for f in LT_FAMILIES if f.name == family.parent)
            except StopIteration:
                raise ValueError(
                    f"Family parent '{family.parent}' of '{family.name}' doesn't exist"
                )
            family.parent = parent
            parent.children.append(family)
        return LT_FAMILIES

    @classmethod
    def get_all_root(cls) -> List["Family"]:
        return [f for f in cls.get_all() if f.parent is None]

    @classmethod
    def get(
        cls,
        any: str = None,
        id: Union[str, int] = None,
        short_name: str = None,
        name: str = None,
        code: str = None,
        description: str = None,
    ) -> "Family":
        if any:
            id = any
            short_name = any
            name = any
            code = any
            description = any
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
            if description and family.description == description:
                return family
        if any:
            raise ValueError(f"Family not found - {any}")
        items = [hex(id) if id else None, short_name, name, code, description]
        text = ", ".join(filter(None, items))
        raise ValueError(f"Family not found - {text}")

    @property
    def has_arduino_core(self) -> bool:
        if isdir(join(LVM.path(), "cores", self.name, "arduino")):
            return True
        if self.parent:
            return self.parent.has_arduino_core
        return False

    @property
    def is_root(self) -> bool:
        return self.parent is None

    @property
    def is_chip(self) -> bool:
        return self.id is not None and self.short_name is not None

    @property
    def is_supported(self) -> bool:
        from ltchiptool import SocInterface

        return any(self.is_child_of(name) for name in SocInterface.get_family_names())

    def is_child_of(self, name: str) -> bool:
        if self.name == name:
            return True
        return self.parent and self.parent.is_child_of(name)

    def is_child_of_code(self, code: str) -> bool:
        if self.code == code:
            return True
        return self.parent and self.parent.is_child_of_code(code)

    @property
    def parent_name(self) -> Optional[str]:
        return self.parent and self.parent.name

    @property
    def parent_code(self) -> Optional[str]:
        return self.parent and self.parent.code

    @property
    def parent_description(self) -> Optional[str]:
        return self.parent and self.parent.description

    @property
    def target_package(self) -> Optional[str]:
        return self.package or self.parent and self.parent.target_package

    @property
    def inheritance(self) -> List["Family"]:
        return (self.parent.inheritance if self.parent else []) + [self]

    def dict(self) -> dict:
        return dict(
            FAMILY=self.short_name,
            FAMILY_NAME=self.name,
            FAMILY_PARENT=self.parent_name,
            FAMILY_CODE=self.code,
            FAMILY_ID=self.id,
            FAMILY_SHORT_NAME=self.short_name,
        )

    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, Family) and self.id == __o.id and self.name == __o.name

    def __iter__(self):
        return iter(self.dict().items())

    def __repr__(self) -> str:
        if self.is_chip:
            return (
                f"<Family: {self.short_name}(0x{self.id:X}), "
                f"name={self.name}, "
                f"parent={self.parent_name}>"
            )
        return (
            f"<Family parent: children({len(self.children)}), "
            f"name={self.name}, "
            f"parent={self.parent_name}>"
        )


class FamilyParamType(click.ParamType):
    name = "family"

    def __init__(self, require_chip: bool = False) -> None:
        super().__init__()
        self.require_chip = require_chip

    def convert(self, value, param, ctx) -> Family:
        try:
            family = Family.get(value)
        except ValueError:
            self.fail(f"Family {value} does not exist", param, ctx)
            return
        if self.require_chip and not family.is_chip:
            raise ValueError(
                f"Family {value} is not a Chip Family - it can't be used here"
            )
        return family

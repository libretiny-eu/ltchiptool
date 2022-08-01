# Copyright (c) Kuba Szczodrzyński 2022-06-02.
from enum import Enum
from typing import Type


def merge_dicts(d1, d2):
    if d1 is not None and type(d1) != type(d2):
        raise TypeError("d1 and d2 are different types")
    if isinstance(d2, list):
        if d1 is None:
            d1 = []
        d1.extend(merge_dicts(None, item) for item in d2)
    elif isinstance(d2, dict):
        if d1 is None:
            d1 = {}
        for key in d2:
            d1[key] = merge_dicts(d1.get(key, None), d2[key])
    else:
        d1 = d2
    return d1


def get(data: dict, path: str):
    if not isinstance(data, dict) or not path:
        return None
    if "." not in path:
        return data.get(path, None)
    key, _, path = path.partition(".")
    return get(data.get(key, None), path)


def has(data: dict, path: str) -> bool:
    if not isinstance(data, dict) or not path:
        return False
    if "." not in path:
        return path in data
    key, _, path = path.partition(".")
    return has(data.get(key, None), path)


def str2enum(cls: Type[Enum], key: str):
    if not key:
        return None
    try:
        return next(e for e in cls if e.name.lower() == key.lower())
    except StopIteration:
        return None

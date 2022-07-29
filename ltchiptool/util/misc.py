# Copyright (c) Kuba Szczodrzyński 2022-06-02.

from functools import update_wrapper

from click import get_current_context


# https://stackoverflow.com/a/1094933/9438331
def sizeof(num: int, suffix="iB", base=1024.0) -> str:
    for unit in ["", "K", "M", "G", "T", "P", "E", "Z"]:
        if abs(num) < base:
            return f"{num:.1f} {unit}{suffix}".replace(".0 ", " ")
        num /= base
    return f"{num:.1f} Y{suffix}".replace(".0 ", " ")


def unpack_obj(f):
    def new_func(*args, **kwargs):
        data = dict(get_current_context().obj)
        data.update(kwargs)
        return f(*args, **data)

    return update_wrapper(new_func, f)

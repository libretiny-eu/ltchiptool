# Copyright (c) Kuba Szczodrzyński 2022-06-02.

from functools import update_wrapper
from typing import List, Tuple

from click import get_current_context


# https://stackoverflow.com/a/1094933/9438331
def sizeof(num: int, suffix="B", base=1024.0) -> str:
    for unit in ["", "K", "M", "G", "T", "P", "E", "Z"]:
        if base == 1024 and unit:
            unit += "i"
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


def list_serial_ports() -> List[Tuple[str, bool, str]]:
    from serial.tools.list_ports import comports

    ports = []
    for port in comports():
        is_usb = port.hwid.startswith("USB")
        if is_usb:
            description = (
                f"{port.name} - {port.description} - "
                f"VID={port.vid:04X} ({port.manufacturer}), "
                f"PID={port.pid:04X} "
            )
        else:
            description = f"{port.name} - {port.description} - HWID={port.hwid}"
        ports.append((port.device, is_usb, description))

    return sorted(ports, key=lambda x: (not x[1], x[2]))

#  Copyright (c) Kuba Szczodrzyński 2022-10-5.

import shlex
from logging import WARNING, warning
from os.path import basename, dirname, join
from typing import Dict, Iterable, List, Optional

import click
from click import Command, Context, MultiCommand

from .fileio import readtext
from .logging import graph
from .misc import list_serial_ports


def get_multi_command_class(cmds: Dict[str, str]):
    class CLIClass(MultiCommand):
        def list_commands(self, ctx: Context) -> List[str]:
            ctx.ensure_object(dict)
            return list(cmds.keys())

        def get_command(self, ctx: Context, cmd_name: str) -> Optional[Command]:
            if cmd_name not in cmds:
                return None
            ns = {}
            fn = join(dirname(__file__), "..", "..", cmds[cmd_name])
            mp = cmds[cmd_name].rpartition("/")[0].replace("/", ".")
            mn = basename(fn).rpartition(".")[0]
            with open(fn) as f:
                code = compile(f.read(), fn, "exec")
                ns["__file__"] = fn
                ns["__name__"] = f"{mp}.{mn}"
                eval(code, ns, ns)
            return ns["cli"]

    return CLIClass


def parse_argfile(args: Iterable[str]) -> List[str]:
    args = list(args)
    try:
        while True:
            i = next(i for i, a in enumerate(args) if a.startswith("@"))
            arg = args.pop(i)
            argv = readtext(arg[1:])
            argv = shlex.split(argv)
            args = args[0:i] + argv + args[i:]
    except StopIteration:
        pass
    return args


def find_serial_port() -> Optional[str]:
    graph(0, "Available COM ports:")
    ports = list_serial_ports()
    if not ports:
        warning("No COM ports found! Use -d/--device to specify the port manually.")
        return None
    for idx, (_, is_usb, description) in enumerate(ports):
        graph(1, description)
        if idx == 0:
            graph(2, "Selecting this port. To override, use -d/--device")
            if not is_usb:
                graph(2, "This is not a USB COM port", loglevel=WARNING)
    return ports[0][0]


class AutoIntParamType(click.ParamType):
    name = "DEC/HEX"

    def convert(self, value, param, ctx) -> int:
        try:
            return int(value, base=0)
        except ValueError as e:
            self.fail(str(e), param, ctx)


class DevicePortParamType(click.ParamType):
    name = "DEVICE"

    def convert(self, value, param, ctx) -> str:
        if isinstance(value, tuple):
            # special default value to auto-detect a serial port
            port = find_serial_port()
            if not port:
                self.fail("No COM ports found", param, ctx)
            return port
        return value

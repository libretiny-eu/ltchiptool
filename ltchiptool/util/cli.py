#  Copyright (c) Kuba Szczodrzyński 2022-10-5.

import shlex
from logging import info
from os.path import basename, dirname, join
from typing import Dict, Iterable, List, Optional

from click import Command, Context, MultiCommand

from .fileio import readtext


def graph(level: int, *message):
    prefix = (level - 1) * "|   " + "|--"
    message = " ".join(str(m) for m in message)
    info(f"{prefix} {message}")


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

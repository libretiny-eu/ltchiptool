#  Copyright (c) Kuba Szczodrzyński 2022-10-5.

from os.path import basename, dirname, join
from typing import Dict, List, Optional

from click import Command, Context, MultiCommand


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

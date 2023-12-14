#  Copyright (c) Kuba Szczodrzyński 2023-1-2.

__all__ = [
    "cli",
]


def cli():
    import sys

    from .__main__ import cli, install_cli

    if len(sys.argv) > 1 and sys.argv[1] == "install":
        sys.argv.pop(1)
        install_cli()
    else:
        cli()

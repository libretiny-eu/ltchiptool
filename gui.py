# Copyright (c) Kuba Szczodrzyński 2023-01-13.

from ltchiptool.gui import cli

if __name__ == "__main__":
    from ltchiptool.util.ltim import LTIM

    LTIM.get().is_gui_entrypoint = True
    cli()

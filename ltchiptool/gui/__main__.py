#  Copyright (c) Kuba Szczodrzyński 2023-1-2.

from logging import error

import click

from ltchiptool import get_version
from ltchiptool.util.logging import VERBOSE, LoggingHandler


def gui_entrypoint():
    try:
        import wx
    except ImportError:
        error("Cannot find wxPython or one of its dependencies")
        error("Refer to https://docs.libretuya.ml/docs/flashing/tools/ltchiptool/")
        exit(1)

    from .main import MainFrame

    app = wx.App()
    try:
        LoggingHandler.get().level = VERBOSE
        frm = MainFrame(None, title=f"ltchiptool v{get_version()}")
        frm.Show()
        app.MainLoop()
    except Exception as e:
        wx.MessageBox(
            message=f"Exception during app initialization\n\n{type(e).__name__}: {e}",
            caption="Error",
            style=wx.ICON_ERROR,
        )
        wx.Exit()
        exit(1)


@click.command(help="Start the GUI")
def cli():
    try:
        gui_entrypoint()
    except Exception as e:
        LoggingHandler.get().emit_exception(e)
        exit(1)


if __name__ == "__main__":
    cli()

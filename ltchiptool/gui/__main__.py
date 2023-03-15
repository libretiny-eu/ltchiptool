#  Copyright (c) Kuba Szczodrzyński 2023-1-2.

import sys
from logging import error

import click

from ltchiptool import get_version
from ltchiptool.util.logging import VERBOSE, LoggingHandler


def gui_entrypoint(*args, **kwargs):
    try:
        import wx
    except ImportError:
        error("Cannot find wxPython or one of its dependencies")
        error("Refer to https://docs.libretuya.ml/docs/flashing/tools/ltchiptool/")
        exit(1)

    app = wx.App()
    try:
        if sys.version_info < (3, 10, 0):
            raise RuntimeError("ltchiptool GUI requires Python 3.10 or newer")
        from .main import MainFrame

        LoggingHandler.get().level = VERBOSE
        frm = MainFrame(None, title=f"ltchiptool v{get_version()}")
        frm.init_params = kwargs
        frm.Show()
        app.MainLoop()
    except Exception as e:
        LoggingHandler.get().exception_hook = None
        LoggingHandler.get().emit_exception(e)
        wx.MessageBox(
            message=f"Exception during app initialization\n\n{type(e).__name__}: {e}",
            caption="Error",
            style=wx.ICON_ERROR,
        )
        wx.Exit()
        exit(1)


@click.command(help="Start the GUI")
@click.argument("FILE", type=str, required=False)
def cli(*args, **kwargs):
    try:
        gui_entrypoint(*args, **kwargs)
    except Exception as e:
        LoggingHandler.get().emit_exception(e)
        exit(1)


if __name__ == "__main__":
    cli()

#  Copyright (c) Kuba Szczodrzyński 2023-1-2.

import sys
from logging import INFO, NOTSET, error, exception

import click

from ltchiptool.util.logging import LoggingHandler
from ltchiptool.util.ltim import LTIM


def gui_entrypoint(*args, **kwargs):
    if sys.version_info < (3, 10, 0):
        error("ltchiptool GUI requires Python 3.10 or newer")
        exit(1)

    try:
        import wx
    except ImportError:
        error("Cannot find wxPython or one of its dependencies")
        error("Refer to https://docs.libretiny.eu/docs/flashing/tools/ltchiptool/")
        exit(1)

    app = wx.App()
    try:
        from .main import MainFrame

        if LoggingHandler.get().level == NOTSET:
            LoggingHandler.get().level = INFO
        frm = MainFrame(None, title=f"ltchiptool {LTIM.get_version_full()}")
        frm.init_params = kwargs
        frm.Show()
        app.MainLoop()
    except Exception as e:
        LoggingHandler.get().exception_hook = None
        exception(None, exc_info=e)
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
        exception(None, exc_info=e)
        exit(1)


if __name__ == "__main__":
    cli()

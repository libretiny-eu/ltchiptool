#  Copyright (c) Kuba Szczodrzyński 2023-1-2.

import sys
from logging import INFO, NOTSET, error, exception
from pathlib import Path

import click

from ltchiptool.util.logging import LoggingHandler
from ltchiptool.util.ltim import LTIM


def gui_entrypoint(install: bool, *args, **kwargs):
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
        if LoggingHandler.get().level == NOTSET:
            LoggingHandler.get().level = INFO

        if not install:
            from .main import MainFrame

            frm = MainFrame(None, title=f"ltchiptool {LTIM.get_version_full()}")
            frm.init_params = kwargs
            frm.Show()
        else:
            from .install import InstallFrame

            frm = InstallFrame(install_kwargs=kwargs, parent=None)
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
        gui_entrypoint(install=False, *args, **kwargs)
    except Exception as e:
        exception(None, exc_info=e)
        exit(1)


@click.command(help="Start the installer")
@click.argument(
    "out_path",
    type=click.Path(
        file_okay=False,
        dir_okay=True,
        writable=True,
        resolve_path=True,
        path_type=Path,
    ),
)
@click.option(
    "--shortcut",
    type=click.Choice(["private", "public"]),
    help="Create a desktop shortcut",
)
@click.option(
    "--fta",
    type=str,
    multiple=True,
    help="File extensions to associate with ltchiptool",
)
@click.option(
    "--add-path",
    is_flag=True,
    help="Add to system PATH",
)
def install_cli(*args, **kwargs):
    try:
        gui_entrypoint(install=True, *args, **kwargs)
    except Exception as e:
        exception(None, exc_info=e)
        exit(1)


if __name__ == "__main__":
    cli()

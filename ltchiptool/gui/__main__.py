#  Copyright (c) Kuba Szczodrzyński 2023-1-2.

from logging import error

import click

from ltchiptool import get_version
from ltchiptool.util import LoggingHandler


def gui():
    import wx

    from .log import GUILoggingHandler
    from .main import MainFrame

    app = wx.App()
    frm = MainFrame(None, title=f"ltchiptool v{get_version()}")
    frm.Show()
    handler: GUILoggingHandler = LoggingHandler.INSTANCE
    handler.print_delayed()
    app.MainLoop()


@click.command(help="Start the GUI")
def cli():
    try:
        import wx
    except ImportError:
        error("Cannot find wxPython or one of its dependencies")
        exit(1)
    gui()


if __name__ == "__main__":
    cli()

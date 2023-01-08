#  Copyright (c) Kuba Szczodrzyński 2022-12-22.

import logging
import sys
from logging import ERROR, LogRecord, StreamHandler, error
from time import time

import click

from .cli import graph

VERBOSE = logging.DEBUG // 2


class LoggingHandler(StreamHandler):
    INSTANCE: "LoggingHandler" = None
    LOG_COLORS = {
        "V": "bright_cyan",
        "D": "bright_blue",
        "I": "bright_green",
        "W": "bright_yellow",
        "E": "bright_red",
        "C": "bright_magenta",
    }

    def __init__(
        self,
        timed: bool = False,
        raw: bool = False,
        indent: int = 0,
    ) -> None:
        super().__init__()
        LoggingHandler.INSTANCE = self
        self.time_start = time()
        self.time_prev = self.time_start
        self.timed = timed
        self.raw = raw
        self.indent = indent

    def emit(self, record: LogRecord) -> None:
        message = record.getMessage()
        if not message:
            return
        self.emit_string(record.levelname[:1], message)

    def emit_string(self, log_prefix: str, message: str, color: str = None):
        now = time()
        elapsed_total = now - self.time_start
        elapsed_current = now - self.time_prev

        log_color = color or self.LOG_COLORS[log_prefix]

        if self.indent:
            empty = (
                not message.strip()
                or message.startswith("|")
                or message.startswith("  ")
            )
            prefix = (self.indent - 1) * "|   "
            prefix += "|   " if empty else "|-- "
            message = prefix + message

        if self.timed:
            message = f"{log_prefix} [{elapsed_total:11.3f}] (+{elapsed_current:5.3f}s) {message}"
        elif not self.raw:
            message = f"{log_prefix}: {message}"

        self.emit_raw(log_prefix, message, log_color)
        self.time_prev += elapsed_current

    def emit_raw(self, log_prefix: str, message: str, color: str):
        file = sys.stderr if log_prefix in "WEC" else sys.stdout
        if self.raw:
            click.echo(message, file=file)
        else:
            click.secho(message, file=file, fg=color)

    @staticmethod
    def tb_echo(tb):
        filename = tb.tb_frame.f_code.co_filename
        name = tb.tb_frame.f_code.co_name
        line = tb.tb_lineno
        graph(1, f'File "{filename}", line {line}, in {name}', loglevel=ERROR)

    @classmethod
    def emit_exception(cls, e: Exception, full_traceback: bool = False):
        error(f"{type(e).__name__}: {e}")
        tb = e.__traceback__
        while tb.tb_next:
            if full_traceback:
                cls.tb_echo(tb)
            tb = tb.tb_next
        cls.tb_echo(tb)


def log_setup(level: int, handler: LoggingHandler, setup_bars: bool = True):
    logging.addLevelName(VERBOSE, "VERBOSE")
    logger = logging.root
    logger.setLevel(level)
    for h in logger.handlers:
        logger.removeHandler(h)
    logger.addHandler(handler)

    # make Click progress bars visible on non-TTY stdout
    if not setup_bars or sys.stdout.isatty():
        return
    # noinspection PyProtectedMember
    from click._termui_impl import ProgressBar

    def render_progress(self: ProgressBar):
        bar = self.format_bar().strip("-")
        if getattr(self, "bar", None) != bar:
            click.echo("#", nl=False)
            self.bar = bar

    def render_finish(_: ProgressBar):
        click.echo("")

    ProgressBar.render_progress = render_progress
    ProgressBar.render_finish = render_finish


def log_copy_setup(logger: str):
    handler = LoggingHandler.INSTANCE
    root = logging.root
    logger = logging.getLogger(logger)
    logger.setLevel(root.level)
    for h in logger.handlers:
        logger.removeHandler(h)
    logger.addHandler(handler)


def verbose(msg, *args, **kwargs):
    logging.log(VERBOSE, msg, *args, **kwargs)

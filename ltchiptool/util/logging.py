#  Copyright (c) Kuba Szczodrzyński 2022-12-22.

import logging
import sys
from logging import LogRecord, StreamHandler
from time import time

import click

VERBOSE = logging.DEBUG // 2
LOG_COLORS = {
    "V": "bright_cyan",
    "D": "bright_blue",
    "I": "bright_green",
    "W": "bright_yellow",
    "E": "bright_red",
    "C": "bright_magenta",
}
VERBOSITY_LEVEL = {
    0: logging.INFO,
    1: logging.DEBUG,
    2: VERBOSE,
}


class LoggingHandler(StreamHandler):
    INSTANCE: "LoggingHandler" = None

    time_start: float
    time_prev: float
    timed: bool = False
    raw: bool = False
    indent: int = 0

    def __init__(self) -> None:
        super().__init__()
        LoggingHandler.INSTANCE = self
        self.time_start = time()
        self.time_prev = self.time_start

    def emit(self, record: LogRecord) -> None:
        message = record.getMessage()
        if not message:
            return
        self.emit_string(record.levelname[:1], message)

    def emit_string(self, log_prefix: str, message: str, color: str = None):
        now = time()
        elapsed_total = now - self.time_start
        elapsed_current = now - self.time_prev

        log_color = color or LOG_COLORS[log_prefix]

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

        file = sys.stderr if log_prefix in "WEC" else sys.stdout

        if self.raw:
            click.echo(message, file=file)
        else:
            click.secho(message, file=file, fg=log_color)
        self.time_prev += elapsed_current


def log_setup(verbosity: int, timed: bool, raw: bool, indent: int):
    verbosity = min(verbosity, 2)
    handler = LoggingHandler()
    handler.timed = timed
    handler.raw = raw
    handler.indent = indent

    logging.addLevelName(VERBOSE, "VERBOSE")
    logger = logging.root
    logger.setLevel(VERBOSITY_LEVEL[verbosity])
    for h in logger.handlers:
        logger.removeHandler(h)
    logger.addHandler(handler)

    # make Click progress bars visible on non-TTY stdout
    if sys.stdout.isatty():
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

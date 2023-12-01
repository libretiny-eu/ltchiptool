#  Copyright (c) Kuba Szczodrzyński 2022-12-22.

import logging
import sys
import threading
from logging import (
    CRITICAL,
    DEBUG,
    ERROR,
    INFO,
    Logger,
    LogRecord,
    StreamHandler,
    error,
    exception,
    log,
)
from time import time
from typing import Callable, Optional

import click

VERBOSE = DEBUG // 2
STREAM = CRITICAL + 1


class LoggingHandler(StreamHandler):
    INSTANCE: "LoggingHandler" = None
    LOG_COLORS = {
        "V": "bright_cyan",
        "D": "bright_blue",
        "I": "bright_green",
        "W": "bright_yellow",
        "E": "bright_red",
        "C": "bright_magenta",
        "S": "bright_magenta",
    }
    exception_hook: Callable[[BaseException, Optional[str]], None] = None

    @staticmethod
    def get() -> "LoggingHandler":
        if LoggingHandler.INSTANCE:
            return LoggingHandler.INSTANCE
        return LoggingHandler()

    def __init__(
        self,
        timed: bool = False,
        raw: bool = False,
        indent: int = 0,
        full_traceback: bool = True,
    ) -> None:
        super().__init__()
        LoggingHandler.INSTANCE = self
        self.time_start = time()
        self.time_prev = self.time_start
        self.timed = timed
        self.raw = raw
        self.indent = indent
        self.full_traceback = full_traceback
        self.emitters = []
        self.attach()
        sys.excepthook = self.excepthook
        threading.excepthook = self.excepthook

    @property
    def level(self):
        return logging.root.level

    @level.setter
    def level(self, value: int):
        logging.root.setLevel(value)

    def attach(self, logger: Logger = None):
        logging.addLevelName(VERBOSE, "VERBOSE")
        logging.addLevelName(STREAM, "STREAM")
        logging.captureWarnings(True)
        if logger:
            root = logging.root
            logger.setLevel(root.level)
        else:
            logger = logging.root
        for h in logger.handlers:
            logger.removeHandler(h)
        logger.addHandler(self)

    def add_emitter(self, emitter: Callable[[str, str, str], None]):
        self.emitters.append(emitter)

    def clear_emitters(self):
        self.emitters.clear()

    def emit(self, record: LogRecord) -> None:
        message = record.msg
        if message and record.args:
            message = message % record.args
        if record.exc_info:
            _, e, _ = record.exc_info
            if e:
                self.emit_exception(e=e, msg=message)
        else:
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
        if file:
            if self.raw:
                click.echo(message, file=file)
            else:
                click.secho(message, file=file, fg=color)
        for emitter in self.emitters:
            emitter(log_prefix, message, color)

    @staticmethod
    def tb_echo(tb):
        filename = tb.tb_frame.f_code.co_filename
        name = tb.tb_frame.f_code.co_name
        line = tb.tb_lineno
        graph(1, f'File "{filename}", line {line}, in {name}', loglevel=ERROR)

    def emit_exception(self, e: BaseException, no_hook: bool = False, msg: str = None):
        original_exc = e
        if msg:
            error(msg)
        while e:
            if e == original_exc:
                error(f"{type(e).__name__}: {e}")
            else:
                error(f"Caused by {type(e).__name__}: {e}")
            tb = e.__traceback__
            if tb:
                while tb.tb_next:
                    if self.full_traceback:
                        self.tb_echo(tb)
                    tb = tb.tb_next
                self.tb_echo(tb)
            e = e.__context__
        if self.exception_hook and not no_hook:
            self.exception_hook(original_exc, msg)

    def excepthook(self, *args):
        if isinstance(args[0], type):
            exception(None, exc_info=args[1])
        else:
            exception(None, exc_info=args[0].exc_value)


def log_setup_click_bars():
    # make Click progress bars visible on non-TTY stdout
    if sys.stdout and sys.stdout.isatty():
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


def verbose(msg, *args, **kwargs):
    logging.log(VERBOSE, msg, *args, **kwargs)


def stream(msg, *args, **kwargs):
    logging.log(STREAM, msg, *args, **kwargs)


def graph(level: int, *message, loglevel: int = INFO):
    prefix = (level - 1) * "|   " + "|-- " if level else ""
    message = " ".join(str(m) for m in message)
    log(loglevel, f"{prefix}{message}")

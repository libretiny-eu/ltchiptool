#  Copyright (c) Kuba Szczodrzyński 2023-5-13.

from logging import debug, warning
from os import stat
from os.path import isfile
from socket import gethostbyname
from time import sleep
from typing import Callable
from urllib.parse import urlparse

import requests
from bk7231tools.analysis.storage import TuyaStorage

from ltchiptool.util.flash import ClickProgressCallback
from ltchiptool.util.logging import LoggingHandler

from .base import BaseThread


class UpkThread(BaseThread):
    def __init__(
        self,
        file: str = None,
        url: str = None,
        on_storage: Callable[[dict], None] = None,
        on_error: Callable[[str], None] = None,
    ):
        super().__init__()
        self.file = file
        self.url = url
        self.on_storage = on_storage
        self.on_error = on_error

    def run_impl(self):
        if self.file is not None:
            self.run_file(self.file)
        if self.url is not None:
            self.run_url(self.url)

    # noinspection HttpUrlsUsage
    def run_url(self, url: str):
        # grab storage data from Kickstart API
        if not url.startswith("http"):
            url = "http://" + url
        url = urlparse(url)
        url = url.netloc
        if not url:
            self.on_error(f"Invalid URL: {url}")
            return

        offset = 0x1E0000
        start = 0x1E0000 - offset
        end = 0x200000 - offset
        init_size = 1024
        block_size = 4096
        buffer = bytearray(end - start)

        with ClickProgressCallback(length=end - start) as bar:
            bar.on_message(f"Resolving {url}...")
            try:
                ip = gethostbyname(url)
            except Exception as e:
                LoggingHandler.get().emit_exception(e, no_hook=True)
                self.on_error(f"Couldn't find hostname: {url}")
                return

            url = f"http://{ip}/hub/flash_read"
            params = dict(offset=0, length=init_size)

            bar.on_message(f"Connecting to {ip}...")
            with requests.get(url, params) as r:
                data = r.content
                if len(data) != init_size:
                    self.on_error(
                        f"Incomplete response read: {len(data)}/{init_size}\n\n"
                        f"Is the chip running Kickstart firmware?"
                    )
                    return

            while start < end and self.should_run():
                bar.on_message(f"Reading from 0x{offset + start:06X}")
                read_size = min(block_size, end - start)
                params["offset"] = offset + start
                params["length"] = read_size
                sleep(0.05)
                with requests.get(url, params) as r:
                    data = r.content
                    if len(data) != read_size:
                        warning(f"Incomplete response read: {len(data)}/{read_size}")
                        sleep(0.2)
                        continue
                    bar.on_update(read_size)
                    buffer[start : start + read_size] = data
                    start += read_size

        if not self.should_run():
            return

        self.run_data(buffer)

    def run_file(self, file: str):
        # read storage from file
        if not isfile(file):
            self.on_error("File not found")
            return
        size = stat(file).st_size
        if size > 0x200000:
            # file too large
            self.on_error("File larger than 2 MiB, refusing to load!")
            return
        if size == 0x200000:
            # probably full flash dump
            with open(file, "rb") as f:
                # seek to approx. storage start (plus a fix for BkWriter etc.)
                f.seek(0x1E0000 - 0x11000)
                data = f.read()
            self.run_data(data)
            return
        # try to search the entire file
        with open(file, "rb") as f:
            data = f.read()
        self.run_data(data)

    def run_data(self, data: bytes):
        # parse raw storage
        st = TuyaStorage()
        if st.load_raw(data, allow_incomplete=True) is None:
            self.on_error("File doesn't contain known storage area")
            return
        if not st.decrypt():
            self.on_error("Couldn't decrypt the storage area")
            return
        keys = st.find_all_keys()
        debug(f"Found {len(keys)} keys! {keys}")
        if not keys:
            self.on_error("No keys found in storage! Is the data corrupt?")
            try:
                from hexdump import hexdump

                hexdump(st.data)
            except (ImportError, ModuleNotFoundError):
                pass
            return
        storage = st.read_all_keys()
        self.on_storage(storage)

    def stop(self):
        super().stop()

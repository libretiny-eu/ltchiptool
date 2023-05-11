#  Copyright (c) Kuba Szczodrzyński 2023-3-18.

import json
import sys
from dataclasses import dataclass, field
from enum import Enum, auto
from logging import debug, warning
from os.path import dirname, expanduser, isdir, isfile, join, realpath
from typing import Dict, List, Optional, Union

from semantic_version import Version
from semantic_version.base import BaseSpec, SimpleSpec


class LVM:
    INSTANCE: "LVM" = None
    platforms: List["LVMPlatform"] = field(default_factory=lambda: [])
    pio = None

    message = (
        f"- if you've opened the .EXE file or installed ltchiptool from PyPI, "
        f"report the error on GitHub issues\n"
        f"- if you're running a git-cloned copy of ltchiptool, install/update "
        f"LibreTiny platform using PlatformIO IDE or CLI\n"
        f"- running the GUI in a git-cloned LT directory will use "
        f"that version, if no other is available"
    )
    compatible_version = SimpleSpec(">0.99.99")

    @staticmethod
    def get(find: bool = True) -> "LVM":
        if LVM.INSTANCE:
            return LVM.INSTANCE
        LVM.INSTANCE = LVM(find)
        return LVM.INSTANCE

    @staticmethod
    def default() -> "LVMPlatform":
        return LVM.get().platforms[0]

    @staticmethod
    def path() -> str:
        return LVM.default().path

    @staticmethod
    def add_path(path: str) -> None:
        lvm = LVM.get(find=False)
        platform = LVMPlatform(
            type=LVMPlatform.Type.RUNTIME,
            path=realpath(path),
            version=LVM.read_version(join(path, "platform.json")),
        )
        lvm.platforms.insert(0, platform)
        lvm.find_all()

    def __init__(self, find: bool = True):
        try:
            from platformio.package.manager.platform import PlatformPackageManager

            self.pio = PlatformPackageManager()
        except (ImportError, AttributeError):
            pass
        self.platforms = []
        if find:
            self.find_all()

    @staticmethod
    def read_version(manifest: str) -> Optional[Version]:
        if not isfile(manifest):
            return None
        with open(manifest, "r") as f:
            data = json.load(f)
        version = data.get("version", None)
        if version:
            return Version(version)
        return None

    def find_all(self) -> None:
        dirs = []

        for name in ["libretiny", "libretuya"]:
            pio_path = expanduser(f"~/.platformio/platforms/{name}")
            if self.pio:
                pkg = self.pio.get_package(name)
                if pkg:
                    pio_path = pkg.path
            dirs += [
                (LVMPlatform.Type.PLATFORMIO, pio_path),
            ]

        if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
            snapshot_path = join(sys._MEIPASS)
        else:
            snapshot_path = join(dirname(__file__), "..")

        dirs += [
            (LVMPlatform.Type.CWD, "."),
            (LVMPlatform.Type.SNAPSHOT, snapshot_path),
        ]

        for dir_type, dir_path in dirs:
            if not (
                isfile(join(dir_path, "platform.json"))
                and isfile(join(dir_path, "families.json"))
            ):
                continue
            platform = LVMPlatform(
                type=dir_type,
                path=realpath(dir_path),
                version=self.read_version(join(dir_path, "platform.json")),
            )
            debug(f"Found {platform}")
            if platform.version not in self.compatible_version:
                warning(
                    f"LibreTiny version outdated (in {platform.path}). "
                    f"Update to v1.0.0 or newer"
                )
            self.platforms.append(platform)

        if not self.platforms:
            raise FileNotFoundError(
                f"Couldn't find required data files\n\n"
                f"Neither LibreTiny package nor local data snapshot could be found.\n\n"
                + self.message
            )

    def require_version(self, spec: BaseSpec = None):
        if not spec:
            spec = self.compatible_version
        for platform in self.platforms:
            if platform.version in spec:
                self.platforms.remove(platform)
                self.platforms.insert(0, platform)
                debug(f"Using v{platform.version} ({platform.path}) as default")
                return
        raise RuntimeError(
            f"Couldn't find required data files\n\n"
            f"LibreTiny platform has been found, but of an "
            f"incompatible version (required is {spec}).\n\n"
            + self.message
            + f"\n\nFound directories:\n"
            + "\n".join(f"- {platform}" for platform in self.platforms)
        )

    def _find_file_platform(self, name: str, version: Union[bool, BaseSpec] = False):
        if version is True:
            spec = self.compatible_version
        elif version is False:
            spec = None
        else:
            spec = version

        incompatible = False
        for platform in self.platforms:
            if not platform.isfile(name):
                continue
            incompatible = True
            if spec and platform.version not in spec:
                continue
            return platform, platform.join(name)
        if incompatible:
            raise RuntimeError(
                f"Couldn't find file: '{name}'\n\n"
                f"LibreTiny platform has been found, but of an "
                f"incompatible version (required is {spec}).\n\n" + self.message
            )
        raise FileNotFoundError(name)

    def find_json(self, name: str, version: Union[bool, BaseSpec] = False) -> str:
        return self._find_file_platform(name, version)[1]

    def load_json(
        self, name: str, version: Union[bool, BaseSpec] = False
    ) -> Union[list, dict]:
        platform, path = self._find_file_platform(name, version)
        return platform.load(path)


@dataclass
class LVMPlatform:
    class Type(Enum):
        PLATFORMIO = auto()
        CWD = auto()
        SNAPSHOT = auto()
        RUNTIME = auto()

    type: Type
    path: str
    version: Optional[Version]
    git_version: Optional[str] = None
    json_cache: Dict[str, Union[list, dict]] = field(default_factory=lambda: {})

    def join(self, path: str) -> str:
        return join(self.path, path)

    def isfile(self, path: str) -> bool:
        return isfile(self.join(path))

    def isdir(self, path: str) -> bool:
        return isdir(self.join(path))

    def load(self, path: str) -> Union[list, dict]:
        if path not in self.json_cache:
            with open(self.join(path), "rb") as f:
                self.json_cache[path] = json.load(f)
        return self.json_cache[path]

    def __str__(self):
        if self.type == LVMPlatform.Type.PLATFORMIO:
            type_name = "PlatformIO Package"
        elif self.type == LVMPlatform.Type.CWD:
            type_name = "Current directory"
        elif self.type == LVMPlatform.Type.SNAPSHOT:
            type_name = "Local data snapshot"
        elif self.type == LVMPlatform.Type.RUNTIME:
            type_name = "PlatformIO (run-time)"
        else:
            type_name = "Unknown"
        return f"{type_name} (v{self.version}) - {self.path}"

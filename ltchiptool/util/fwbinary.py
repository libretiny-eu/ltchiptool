#  Copyright (c) Kuba Szczodrzyński 2023-4-11.

import json
from dataclasses import dataclass
from os.path import basename, dirname, isdir, isfile, join
from typing import IO, Dict, List, Optional, Union

from ltchiptool.util.fileio import isnewer
from ltchiptool.util.logging import graph

GROUPS: Dict[str, List["FirmwareBinary"]] = {}


@dataclass
class FirmwareBinary:
    location: str
    name: str
    subname: Optional[str] = None
    offset: Optional[int] = None
    ext: str = "bin"

    title: Optional[str] = None
    description: Optional[str] = None
    public: bool = False

    filename: str = None

    def __post_init__(self) -> None:
        if isfile(self.location):
            self.location = dirname(self.location)
        elif not isdir(self.location):
            raise NotADirectoryError(self.location)

        spec = [
            self.subname,
            self.offset is not None and f"0x{self.offset:06X}",
            self.ext,
        ]
        suffix = ".".join(s for s in spec if s)
        self.filename = f"image_{self.name}.{suffix}".rstrip(".")

        if self.location not in GROUPS:
            GROUPS[self.location] = []
        GROUPS[self.location].append(self)

    @staticmethod
    def load(location: str, obj: dict) -> "FirmwareBinary":
        filename = obj["filename"]
        filename = filename.split(".")

        name = filename[0][6:]  # strip "image_"
        subname = None
        offset = None
        ext = filename[-1]

        if len(filename) > 2 and filename[-2].startswith("0x"):
            offset = int(filename[-2])
            filename.pop(-2)
        if len(filename) > 2:
            subname = ".".join(filename[1:-1])

        return FirmwareBinary(
            location=location,
            name=name,
            subname=subname,
            offset=offset,
            ext=ext,
            title=obj["title"],
            description=obj["description"],
            public=obj["public"],
        )

    @property
    def path(self) -> str:
        return join(self.location, self.filename)

    def graph(self, indent: int = 1) -> None:
        graph(indent, basename(self.filename))

    def write(self) -> IO[bytes]:
        return open(self.path, "wb")

    def isnewer(self, than: Union[str, "FirmwareBinary"]) -> bool:
        if isinstance(than, FirmwareBinary):
            return isnewer(self.path, than.path)
        return isnewer(self.path, than)

    def group_get(self) -> List["FirmwareBinary"]:
        return GROUPS[self.location]

    def group_write(self) -> None:
        files = []
        group = self.group_get()
        for file in group:
            if file.description is None and self.offset is not None:
                self.description = f"For flashing directly"
            files.append(
                {
                    "title": file.title,
                    "description": file.description,
                    "filename": file.filename,
                    "offset": file.offset,
                    "public": file.public,
                }
            )
        with open(join(self.location, "firmware.json"), "w") as f:
            json.dump(files, f, indent="\t")

    def group(self) -> List["FirmwareBinary"]:
        self.group_write()
        return list(self.group_get())

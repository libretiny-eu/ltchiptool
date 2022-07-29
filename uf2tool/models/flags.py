# Copyright (c) Kuba Szczodrzyński 2022-05-27.


class Flags:
    not_main_flash: bool = False
    file_container: bool = False
    has_family_id: bool = False
    has_md5: bool = False
    has_tags: bool = False

    def encode(self) -> int:
        val = 0
        if self.not_main_flash:
            val |= 0x00000001
        if self.file_container:
            val |= 0x00001000
        if self.has_family_id:
            val |= 0x00002000
        if self.has_md5:
            val |= 0x00004000
        if self.has_tags:
            val |= 0x00008000
        return val

    def decode(self, data: int):
        self.not_main_flash = (data & 0x00000001) != 0
        self.file_container = (data & 0x00001000) != 0
        self.has_family_id = (data & 0x00002000) != 0
        self.has_md5 = (data & 0x00004000) != 0
        self.has_tags = (data & 0x00008000) != 0

    def __str__(self) -> str:
        flags = []
        if self.not_main_flash:
            flags.append("NMF")
        if self.file_container:
            flags.append("FC")
        if self.has_family_id:
            flags.append("FID")
        if self.has_md5:
            flags.append("MD5")
        if self.has_tags:
            flags.append("TAG")
        return ",".join(flags)

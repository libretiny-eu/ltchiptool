# Copyright (c) Kuba Szczodrzyński 2022-07-29.

from .obj import get, has


class RecursiveDict(dict):
    def __getitem__(self, k):
        return get(self, k)

    def __contains__(self, o) -> bool:
        if "." not in o:
            return super(RecursiveDict, self).__contains__(o)
        return has(self, str(o))

#  Copyright (c) Kuba Szczodrzyński 2023-1-9.

from warnings import warn

warn(
    "PortWatcher has been removed, please use DevicesBase instead",
    stacklevel=2,
)


class PortWatcher:
    pass

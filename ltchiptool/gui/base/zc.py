#  Copyright (c) Kuba Szczodrzyński 2023-11-28.

from warnings import warn

warn(
    "ltchiptool.gui.base.zc is deprecated, " "migrate to ltchiptool.gui.mixin.zc",
    stacklevel=2,
)

from ltchiptool.gui.mixin.zc import ZeroconfBase

__deprecated__ = ZeroconfBase

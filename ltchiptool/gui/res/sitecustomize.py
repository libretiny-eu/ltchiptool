#  Copyright (c) Kuba Szczodrzyński 2024-3-6.

import os
import sys
from pathlib import Path

# resulting path matches click.get_app_dir()
if sys.platform.startswith("win"):
    env = os.environ.get("APPDATA")
    if env is None:
        data_path = Path("~")
    else:
        data_path = Path(env)
elif sys.platform == "darwin":
    data_path = Path("~/Library/Application Support")
else:
    env = os.environ.get("XDG_CONFIG_HOME")
    if env is None:
        data_path = Path("~/.config")
    else:
        data_path = Path(env)

site_path = data_path.expanduser().resolve() / "ltchiptool" / "site-packages"
sys.path.insert(0, str(site_path))
setattr(sys, "_LTCHIPTOOLSITE", site_path)

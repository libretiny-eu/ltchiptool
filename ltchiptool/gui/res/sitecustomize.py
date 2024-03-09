#  Copyright (c) Kuba Szczodrzyński 2024-3-6.

import os
import site
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

data_path = data_path.expanduser().resolve() / "ltchiptool"
os.environ["PYTHONUSERBASE"] = str(data_path)

site.ENABLE_USER_SITE = True
site.USER_SITE = None
site.USER_BASE = None

site_path = Path(site.getusersitepackages())
sys.path.insert(0, str(site_path))
setattr(sys, "_LTCHIPTOOLSITE", site_path)

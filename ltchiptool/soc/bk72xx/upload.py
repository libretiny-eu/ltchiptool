# Copyright (c) Kuba Szczodrzyński 2022-07-29.

import sys

from uf2tool import UploadContext


# noinspection PyUnresolvedReferences
def import_bkserial() -> type:
    try:
        from platformio.package.manager.tool import ToolPackageManager

        manager = ToolPackageManager()
        pkg = manager.get_package("tool-bk7231tools")
        sys.path.append(pkg.path)
        from bk7231tools.serial import BK7231Serial
    except (ImportError, AttributeError):
        raise RuntimeError(
            "You need PlatformIO and tool-bk7231tools package to run this program."
        )
    return BK7231Serial


# noinspection PyUnusedLocal
def upload(
    ctx: UploadContext,
    port: str,
    baud: int = None,
    timeout: float = None,
    **kwargs,
):
    # noinspection PyPep8Naming
    BK7231Serial = import_bkserial()

    prefix = "|   |--"
    baudrate = baud or ctx.baudrate or 115200
    print(prefix, f"Trying to link on {port} @ {baudrate}")
    # connect to chip
    bk = BK7231Serial(port=port, baudrate=baudrate, link_timeout=timeout or 10.0)

    # collect continuous blocks of data
    parts = ctx.collect(ota_idx=1)
    # write blocks to flash
    for offs, data in parts.items():
        length = len(data.getvalue())
        data.seek(0)
        print(prefix, f"Writing {length} bytes to 0x{offs:06x}")
        try:
            bk.program_flash(
                data,
                length,
                offs,
                verbose=False,
                crc_check=True,
                dry_run=False,
                really_erase=True,
            )
        except ValueError as e:
            raise RuntimeError(f"Writing failed: {e.args[0]}")
    # reboot the chip
    bk.reboot_chip()

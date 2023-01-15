#  Copyright (c) Kuba Szczodrzyński 2022-12-23.

from logging import debug

from ltchiptool import SocInterface
from ltchiptool.util.flash import format_flash_guide
from ltchiptool.util.logging import LoggingHandler, graph


def flash_link_interactive(soc: SocInterface, link_timeout: float):
    graph(
        0,
        f"Connecting to '{soc.family.description}' "
        f"on {soc.conn.port} @ {soc.conn.link_baudrate}",
    )
    prev_timeout = soc.conn.link_timeout

    for stage in range(4):
        debug(f"Linking: stage {stage}")
        if stage == 0:
            # use timeout of 1.0s to check if already linked
            soc.flash_change_timeout(link_timeout=2.0)
        elif stage == 1:
            # try hardware GPIO reset
            soc.flash_hw_reset()
        elif stage == 2:
            # guide the user to connect the chip properly, or reset it manually
            soc.flash_change_timeout(link_timeout=link_timeout or prev_timeout)
            for line in format_flash_guide(soc):
                LoggingHandler.get().emit_string("I", line, color="bright_blue")
        else:
            # give up after link_timeout
            raise TimeoutError("Timeout while linking with the chip")

        try:
            soc.flash_disconnect()
            soc.flash_connect()
            break
        except TimeoutError:
            stage += 1

    # successfully linked
    chip_info = soc.flash_get_chip_info_string()
    graph(1, f"Success! Chip info: {chip_info}")

#  Copyright (c) Kuba Szczodrzyński 2022-12-23.

from logging import debug

from ltchiptool import SocInterface
from ltchiptool.util.flash import format_flash_guide
from ltchiptool.util.logging import LoggingHandler, graph


def flash_link_interactive(
    soc: SocInterface,
    port: str,
    baud: int,
    link_timeout: float,
):
    for stage in range(4):
        debug(f"Linking: stage {stage}")
        if stage == 0:
            # use timeout of 1.0s to check if already linked
            soc.set_uart_params(port=port, baud=baud, link_timeout=2.0)
        elif stage == 1:
            # try hardware GPIO reset
            soc.flash_hw_reset()
        elif stage == 2:
            # guide the user to connect the chip properly, or reset it manually
            soc.set_uart_params(port=port, baud=baud, link_timeout=link_timeout or 20.0)
            for line in format_flash_guide(soc):
                LoggingHandler.get().emit_string("I", line, color="bright_blue")
        else:
            # give up after link_timeout
            raise TimeoutError("Timeout while linking with the chip")

        try:
            if stage == 0:
                # print once, but after setting port and baud
                graph(
                    0,
                    f"Connecting to '{soc.family.description}' "
                    f"on {soc.port} @ {soc.baud}",
                )
            soc.flash_disconnect()
            soc.flash_connect()
            break
        except TimeoutError:
            stage += 1

    # successfully linked
    chip_info = soc.flash_get_chip_info_string()
    graph(1, f"Success! Chip info: {chip_info}")

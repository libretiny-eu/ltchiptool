# Copyright (c) Kuba Szczodrzyński 2022-07-29.

from abc import ABC
from typing import IO, Dict, Generator, List, Optional, Tuple, Union

from ltchiptool import Board, Family
from ltchiptool.models import OTAType
from ltchiptool.util.flash import FlashConnection, FlashFeatures, FlashMemoryType
from ltchiptool.util.fwbinary import FirmwareBinary
from ltchiptool.util.streams import ProgressCallback
from uf2tool import UploadContext


class SocInterface(ABC):
    family: Family = None
    board: Board = None
    conn: FlashConnection = None

    @classmethod
    def get(cls, family: Family) -> "SocInterface":
        # fmt: off
        if family.is_child_of("beken-72xx"):
            from .bk72xx import BK72XXMain
            return BK72XXMain(family)
        if family.is_child_of("realtek-ambz"):
            from .ambz import AmebaZMain
            return AmebaZMain(family)
        if family.is_child_of("realtek-ambz2"):
            from .ambz2 import AmebaZ2Main
            return AmebaZ2Main(family)
        # fmt: on
        raise NotImplementedError(f"Unsupported family - {family.name}")

    @classmethod
    def get_family_names(cls) -> List[str]:
        """Return family names (or parent names) implemented in SocInterface."""
        return [
            "beken-72xx",
            "realtek-ambz",
            "realtek-ambz2",
        ]

    #########################
    # Common helper methods #
    #########################

    def set_board(self, board: Board):
        self.board = board

    #####################################################
    # Abstract methods - implemented by the SoC modules #
    #####################################################

    def hello(self):
        raise NotImplementedError()

    @property
    def ota_type(self) -> Optional[OTAType]:
        raise NotImplementedError()

    @property
    def ota_supports_format_1(self) -> bool:
        """Returns True if the chip family should support legacy OTA."""
        return False

    ##################################
    # Linking - ELF and BIN building #
    ##################################

    def link2elf(
        self,
        ota1: str,
        ota2: str,
        args: List[str],
    ) -> Dict[int, str]:
        raise NotImplementedError()

    def elf2bin(
        self,
        input: str,
        ota_idx: int,
    ) -> List[FirmwareBinary]:
        raise NotImplementedError()

    def link2bin(
        self,
        ota1: str,
        ota2: str,
        args: List[str],
    ) -> List[FirmwareBinary]:
        raise NotImplementedError()

    def detect_file_type(
        self,
        file: IO[bytes],
        length: int,
    ) -> Optional["Detection"]:
        """
        Check if the file is flashable to this SoC.

        :return: a Detection object with results, or None if type unknown
        """
        raise NotImplementedError()

    #########################################################
    # Flashing - reading/writing raw files and UF2 packages #
    #########################################################

    def flash_get_features(self) -> FlashFeatures:
        """Check which flasher features are supported."""
        return FlashFeatures()  # Optional; do not fail here

    def flash_get_guide(self) -> List[Union[str, list]]:
        """Get a short textual guide for putting the chip in download mode."""
        return []  # Optional; do not fail here

    def flash_get_docs_url(self) -> Optional[str]:
        """Get a link to flashing documentation."""
        return None  # Optional; do not fail here

    def flash_set_connection(self, connection: FlashConnection) -> None:
        """Configure device connection parameters."""
        raise NotImplementedError()

    def flash_build_protocol(self, force: bool = False) -> None:
        """Create an instance of flashing protocol class. Only used internally."""
        raise NotImplementedError()

    def flash_change_timeout(self, timeout: float = 0.0, link_timeout: float = 0.0):
        """Change device connection timeout values."""
        raise NotImplementedError()

    def flash_sw_reset(self) -> None:
        """Perform a software reset by transmitting a magic word."""
        pass  # Optional; do not fail here

    def flash_hw_reset(self) -> None:
        """Perform a hardware reset using UART GPIO lines."""
        pass  # Optional; do not fail here

    def flash_connect(self) -> None:
        """Link with the chip for read/write operations. Do nothing if
        already linked or not supported."""
        raise NotImplementedError()

    def flash_disconnect(self) -> None:
        """Close the serial port, if it's open."""
        raise NotImplementedError()

    def flash_get_chip_info(self) -> List[Tuple[str, str]]:
        """Read all available chip info as a dictionary."""
        raise NotImplementedError()

    def flash_get_chip_info_string(self) -> str:
        """Read chip info **summary** from the protocol as a string."""
        raise NotImplementedError()

    def flash_get_size(self, memory: FlashMemoryType = FlashMemoryType.FLASH) -> int:
        """Retrieve the size of specified memory, in bytes.
        Raises NotImplementedError() if the memory type is not available
        or not readable."""
        raise NotImplementedError()

    def flash_get_rom_size(self) -> int:
        """Deprecated, use flash_get_size(FlashMemoryType.ROM)."""
        return self.flash_get_size(FlashMemoryType.ROM)

    def flash_read_raw(
        self,
        offset: int,
        length: int,
        verify: bool = True,
        memory: FlashMemoryType = FlashMemoryType.FLASH,
        callback: ProgressCallback = ProgressCallback(),
    ) -> Generator[bytes, None, None]:
        """
        Read 'length' bytes from the chip, starting at 'offset'.

        :param offset: start memory offset
        :param length: length of data to read
        :param verify: whether to verify checksums
        :param memory: type of memory to read from
        :param callback: reading progress callback
        :return: a generator yielding the chunks being read
        """
        raise NotImplementedError()

    def flash_write_raw(
        self,
        offset: int,
        length: int,
        data: IO[bytes],
        verify: bool = True,
        callback: ProgressCallback = ProgressCallback(),
    ) -> None:
        """
        Write 'length' bytes (represented by 'data') to the chip, starting at 'offset'.

        :param offset: start memory offset
        :param length: length of data to write
        :param data: IO stream of data to write
        :param verify: whether to verify checksums
        :param callback: writing progress callback
        """
        raise NotImplementedError()

    def flash_write_uf2(
        self,
        ctx: UploadContext,
        verify: bool = True,
        callback: ProgressCallback = ProgressCallback(),
    ) -> None:
        """
        Upload an UF2 package to the chip.

        :param ctx: UF2 uploading context
        :param verify: whether to verify checksums
        :param callback: writing progress callback
        """
        raise NotImplementedError()

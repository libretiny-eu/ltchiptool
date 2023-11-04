#  Copyright (c) Kuba Szczodrzyński 2023-11-2.

from ltchiptool.util.intbin import inttole32

AMBZ_DATA_ADDRESS = 0x10003000


class AmbZCode:
    @staticmethod
    def rom_console() -> bytes:
        # push {r3, lr}
        # ldr r4, RtlConsolRom
        # mov.w r0, #1000
        # blx r4
        # b #4
        # RtlConsolRom: .word 0x2204+1
        return (
            b"\x08\xb5\x02\x4c"
            b"\x4f\xf4\x7a\x70"
            b"\xa0\x47\xfb\xe7"
            b"\x05\x22\x00\x00"  # RtlConsolRom()
        )

    @staticmethod
    def print_greeting(delay: float, data: bytes) -> bytes:
        # ldr r0, ms_delay
        # ldr r3, DelayMs
        # blx r3
        # adr r0, message_data
        # ldr r1, message_size
        # ldr r3, xmodem_uart_putdata
        # blx r3
        # b next
        # DelayMs: .word 0x346C+1
        # xmodem_uart_putdata: .word 0xEC48+1
        # ms_delay: .word 1000
        # message_size: .word 16
        # message_data: .word 0,0,0,0
        # next:
        ms_delay = int(delay * 1000)
        message_size = len(data)
        if message_size > 16:
            raise ValueError("Message must be 16 bytes or shorter")
        message_data = data.ljust(16, b"\x00")
        return (
            (
                b"\x05\x48\x03\x4b"
                b"\x98\x47\x06\xa0"
                b"\x04\x49\x02\x4b"
                b"\x98\x47\x0f\xe0"
                b"\x6d\x34\x00\x00"  # DelayMs()
                b"\x49\xec\x00\x00"  # xmodem_uart_putdata()
            )
            + inttole32(ms_delay)
            + inttole32(message_size)
            + message_data
        )

    @staticmethod
    def download_mode() -> bytes:
        """Disable booting to SRAM and run download mode again."""
        # ldr r3, uartimg_boot_sram
        # ldr r0, [r3]
        # ldr r1, uartimg_boot_mask
        # ands r0, r0, r1
        # str r0, [r3]
        # movs r0, #2
        # ldr r3, UARTIMG_Download
        # blx r3
        # UARTIMG_Download: .word 0x900+1
        # uartimg_boot_sram: .word 0x40000210
        # uartimg_boot_mask: .word 0xEFFFFFFF
        return (
            b"\x04\x4b\x18\x68"
            b"\x04\x49\x08\x40"
            b"\x18\x60\x02\x20"
            b"\x00\x4b\x98\x47"
            b"\x01\x09\x00\x00"  # UARTIMG_Download()
            b"\x10\x02\x00\x40"  # uartimg_boot_sram
            b"\xff\xff\xff\xef"  # uartimg_boot_mask
        )

    @staticmethod
    def uart_set_baud_rate(baudrate: int) -> bytes:
        # ldr r0, XComUARTx
        # ldr r0, [r0]
        # ldr r3, UART_WaitBusy
        # movs r1, #10
        # blx r3
        # ldr r0, XComUARTx
        # ldr r0, [r0]
        # ldr r1, baud_rate
        # ldr r3, UART_SetBaud
        # blx r3
        # b next
        # movs r0, r0
        # XComUARTx: .word 0x10000FC4
        # UART_WaitBusy: .word 0xC1F8+1
        # UART_SetBaud: .word 0xBF00+1
        # baud_rate: .word 115200
        # next:
        return (
            b"\x05\x48\x00\x68"
            b"\x05\x4b\x0a\x21"
            b"\x98\x47\x03\x48"
            b"\x00\x68\x05\x49"
            b"\x03\x4b\x98\x47"
            b"\x08\xe0\x00\x00"
            b"\xc4\x0f\x00\x10"  # XComUARTx
            b"\xf9\xc1\x00\x00"  # UART_WaitBusy()
            b"\x01\xbf\x00\x00"  # UART_SetBaud()
        ) + inttole32(baudrate)

    @staticmethod
    def read_flash_id(offset: int = 0) -> bytes:
        # movs r0, #0x9F
        # movs r1, #3
        # ldr r2, read_data
        # ldr r3, FLASH_RxCmd
        # blx r3
        # b next
        # FLASH_RxCmd: .word 0x7464+1
        # read_data: .word 0x10003000
        # next:
        return (
            b"\x9f\x20\x03\x21"
            b"\x02\x4a\x01\x4b"
            b"\x98\x47\x03\xe0"
            b"\x65\x74\x00\x00"  # FLASH_RxCmd()
        ) + inttole32(AMBZ_DATA_ADDRESS + offset)

    @staticmethod
    def read_chip_id(offset: int = 0) -> bytes:
        # ldr r0, CtrlSetting
        # movs r1, #0xF8
        # ldr r2, read_data
        # movs r3, #7
        # ldr r4, EFUSE_OneByteReadROM
        # blx r4
        # b next
        # movs r0, r0
        # CtrlSetting: .word 9902
        # EFUSE_OneByteReadROM: .word 0x6D64+1
        # read_data: .word 0x10003000
        # next:
        return (
            b"\x03\x48\xf8\x21"
            b"\x04\x4a\x07\x23"
            b"\x02\x4c\xa0\x47"
            b"\x06\xe0\x00\x00"
            b"\xae\x26\x00\x00"  # CtrlSetting
            b"\x65\x6d\x00\x00"  # EFUSE_OneByteReadROM()
        ) + inttole32(AMBZ_DATA_ADDRESS + offset)

    @staticmethod
    def read_efuse_raw(start: int = 0, length: int = 256, offset: int = 0) -> bytes:
        # ldr r5, start
        # loop:
        # ldr r0, CtrlSetting
        # movs r1, r5
        # ldr r2, read_data
        # adds r2, r2, r5
        # movs r3, #7
        # ldr r4, EFUSE_OneByteReadROM
        # blx r4
        # adds r5, r5, #1
        # ldr r0, length
        # cmp r5, r0
        # bne loop
        # b next
        # movs r0, r0
        # CtrlSetting: .word 9902
        # EFUSE_OneByteReadROM: .word 0x6D64+1
        # read_data: .word 0x10003000
        # start: .word 0
        # length: .word 256
        # next:
        return (
            (
                b"\x09\x4d\x06\x48"
                b"\x29\x00\x07\x4a"
                b"\x52\x19\x07\x23"
                b"\x04\x4c\xa0\x47"
                b"\x6d\x1c\x06\x48"
                b"\x85\x42\xf4\xd1"
                b"\x0a\xe0\x00\x00"
                b"\xae\x26\x00\x00"  # CtrlSetting
                b"\x65\x6d\x00\x00"  # EFUSE_OneByteReadROM()
            )
            + inttole32(AMBZ_DATA_ADDRESS + offset)
            + inttole32(start)
            + inttole32(length)
        )

    @staticmethod
    def read_efuse_otp(offset: int = 0) -> bytes:
        # ldr r0, read_data
        # ldr r3, EFUSE_OTP_Read32B
        # blx r3
        # b next
        # EFUSE_OTP_Read32B: .word 0x3C20+1
        # read_data: .word 0x10003000
        # next:
        return (
            b"\x02\x48\x01\x4b"
            b"\x98\x47\x03\xe0"
            b"\x21\x3C\x00\x00"  # EFUSE_OTP_Read32B()
        ) + inttole32(AMBZ_DATA_ADDRESS + offset)

    @staticmethod
    def read_efuse_logical_map(offset: int = 0) -> bytes:
        # ldr r0, read_data
        # ldr r3, EFUSE_LogicalMap_Read
        # blx r3
        # b next
        # EFUSE_LogicalMap_Read: .word 0x7090+1
        # read_data: .word 0x10003000
        # next:
        return (
            b"\x02\x48\x01\x4b"
            b"\x98\x47\x03\xe0"
            b"\x91\x70\x00\x00"  # EFUSE_LogicalMap_Read()
        ) + inttole32(AMBZ_DATA_ADDRESS + offset)

    @staticmethod
    def read_data_md5(address: int, length: int, offset: int = 0) -> bytes:
        # ldr r0, context
        # ldr r3, rt_md5_init
        # blx r3
        # ldr r0, context
        # ldr r1, input
        # ldr r2, length
        # ldr r3, rt_md5_append
        # blx r3
        # ldr r0, digest
        # ldr r1, context
        # ldr r3, rt_md5_final
        # blx r3
        # b next
        # movs r0, r0
        # rt_md5_init: .word 0x11DF4+1
        # rt_md5_append: .word 0x11E24+1
        # rt_md5_final: .word 0x11EC8+1
        # input: .word 0
        # length: .word 0
        # digest: .word 0
        # context: .word 0
        # next:
        return (
            (
                b"\x0c\x48\x06\x4b"
                b"\x98\x47\x0b\x48"
                b"\x07\x49\x08\x4a"
                b"\x04\x4b\x98\x47"
                b"\x07\x48\x08\x49"
                b"\x03\x4b\x98\x47"
                b"\x0e\xe0\x00\x00"
                b"\xf5\x1d\x01\x00"  # rt_md5_init()
                b"\x25\x1e\x01\x00"  # rt_md5_append()
                b"\xc9\x1e\x01\x00"  # rt_md5_final()
            )
            + inttole32(address)
            + inttole32(length)
            + inttole32(AMBZ_DATA_ADDRESS + offset)
            + inttole32(AMBZ_DATA_ADDRESS + offset + 16)
        )

    @staticmethod
    def print_data(length: int, address: int = AMBZ_DATA_ADDRESS) -> bytes:
        # ldr r0, address
        # ldr r1, length
        # ldr r3, xmodem_uart_putdata
        # blx r3
        # b next
        # movs r0, r0
        # xmodem_uart_putdata: .word 0xEC48+1
        # address: .word 0x10003000
        # length: .word 4
        # next:
        return (
            (
                b"\x03\x48\x04\x49"
                b"\x01\x4b\x98\x47"
                b"\x06\xe0\x00\x00"
                b"\x49\xec\x00\x00"  # xmodem_uart_putdata()
            )
            + inttole32(address)
            + inttole32(length)
        )

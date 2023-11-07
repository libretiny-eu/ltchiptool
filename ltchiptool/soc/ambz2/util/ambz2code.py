#  Copyright (c) Kuba Szczodrzyński 2023-11-7.

AMBZ2_CODE_EFUSE_READ = (
    # push {r3-r5,lr}
    # movs r5, #0
    # loop:
    # ldr r0, EFUSE_CTRL_SETTING
    # movs r1, r5
    # ldr r2, read_data
    # add r2, r5
    # movs r3, #0xAA
    # strb r3, [r2]
    # movs r3, #0
    # ldr r4, hal_efuse_stubs
    # adds r4, r4, #8
    # ldr r4, [r4]
    # blx r4
    # ldr r3, read_size
    # adds r5, r5, #1
    # cmp r5, r3
    # bne loop
    # pop {r3-r5,pc}
    # EFUSE_CTRL_SETTING: .word 0x33300000
    # hal_efuse_stubs: .word 0x500
    # read_size: .word 512
    # read_data: .word 0x10038000
    b"\x38\xb5\x00\x25"
    b"\x07\x48\x29\x00"
    b"\x09\x4a\x2a\x44"
    b"\xaa\x23\x13\x70"
    b"\x00\x23\x05\x4c"
    b"\x08\x34\x24\x68"
    b"\xa0\x47\x04\x4b"
    b"\x6d\x1c\x9d\x42"
    b"\xf0\xd1\x38\xbd"
    b"\x00\x00\x30\x33"  # EFUSE_CTRL_SETTING
    b"\x00\x05\x00\x00"  # hal_efuse_stubs
    b"\x00\x02\x00\x00"  # read_size
    b"\x00\x80\x03\x10"  # read_data
)

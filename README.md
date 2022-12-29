# ltchiptool

Tools for working with LT-supported IoT chips.

## What is this?

This repository is a collection of tools, used in the [LibreTuya project](https://github.com/kuba2k2/libretuya), that perform some chip-specific tasks, like packaging binary images or uploading firmware to the chip.

Since v2.0.0, it contains a common, chip-independent CLI and API for interacting with supported chips in download mode (reading/writing flash).

## Installation

From PyPI:

```shell
pip install ltchiptool
```

This will install `ltchiptool` and `uf2tool` packages.

## Usage

```shell
$ ltchiptool --help
Usage: ltchiptool [OPTIONS] COMMAND [ARGS]...

  Tools for working with LT-supported IoT chips

Options:
  -v, --verbose         Output debugging messages (repeat to output more)
  -T, --traceback       Print complete exception traceback
  -t, --timed           Prepend log lines with timing info
  -r, --raw-log         Output logging messages with no additional styling
  -i, --indent INTEGER  Indent log messages using graph lines
  -V, --version         Show the version and exit.
  -h, --help            Show this message and exit.

Commands:
  dump      Capture or process device dumps
  elf2bin   Generate firmware binaries from ELF file
  flash     Flashing tool - reading/writing
  link2bin  Link code to binary format
  list      List boards, families, etc.
  soc       Run SoC-specific tools
  uf2       Work with UF2 files
```

## Flashing/dumping

There are three main commands used for flashing:
- `ltchiptool flash file <FILE>` - detect file type based on its contents (i.e. chip from which a dump was acquired), similar to Linux `file` command
- `ltchiptool flash read <FAMILY> <FILE>` - make a full flash dump of the connected device; specifying the family is required
- `ltchiptool flash write <FILE>` - upload a file to the device; detects file type automatically (just like the `file` command above)

Supported device families can be checked using `ltchiptool list families` command. In the commands above, you can use any of the family names (name/code/short name/etc).

The upload UART port and baud rate is detected automatically. To override it, use `-d COMx` or `-d /dev/ttyUSBx`. To change the target baud rate, use `-b 460800`.
Note that the baud rate is changed after linking. Linking is performed using chip-default baud rate.

It's not required to specify chip family for writing files - `ltchiptool` tries to recognize contents of the file, and chooses the best settings automatically.
If you want to flash unrecognized/raw binaries (or fine-tune the flashing parameters), specify `-f <FAMILY>` and `-s <START OFFSET>`.

## UF2 Example

```shell
$ ltchiptool uf2 info ./arduinotest_22.08.01_wb2l_BK7231T_lt0.8.0.uf2
Family: BK7231T / Beken 7231T
Tags:
 - BOARD: wb2l
 - DEVICE_ID: d80e20c2
 - LT_VERSION: 0.8.0
 - FIRMWARE: arduinotest
 - VERSION: 22.08.01
 - OTA_VERSION: 01
 - DEVICE: LibreTuya
 - BUILD_DATE: 6d08e862
 - LT_HAS_OTA1: 01
 - LT_HAS_OTA2: 00
 - LT_PART_1: app
 - LT_PART_2:
Data chunks: 1871
Total binary size: 478788
```

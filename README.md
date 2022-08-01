# ltchiptool

Tools for working with LT-supported IoT chips.

## What is this?

This repository is a collection of tools, used in the [LibreTuya project](https://github.com/kuba2k2/libretuya), that perform some chip-specific tasks, like packaging binary images or uploading firmware to the chip.

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
  --help  Show this message and exit.

Commands:
  link2bin  Link code to binary format
  elf2bin   Generate firmware binaries from ELF file
  uf2       Work with UF2 files
```

## Examples

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

```shell
$ ltchiptool uf2 upload arduinotest_22.08.01_wb2l_BK7231T_lt0.8.0.uf2 uart COM60
|-- arduinotest 22.08.01 @ 2022-08-01 19:07:57 -> wb2l
|-- Using UART
|   |-- Trying to link on COM60 @ 921600
...
```

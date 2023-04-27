/* Copyright (c) Kuba Szczodrzyński 2022-05-28. */

#pragma once

#include <stdbool.h>
#include <stdint.h>

#define UF2_MAGIC_1 0x0A324655
#define UF2_MAGIC_2 0x9E5D5157
#define UF2_MAGIC_3 0x0AB16F30

#define UF2_BLOCK_SIZE sizeof(uf2_block_t)

#define UF2OTA_VERSION 40000

struct fal_partition;

#ifdef __MINGW_GCC_VERSION
typedef struct __attribute__((gcc_struct, packed, aligned(1)))
#else
typedef struct __attribute__((packed))
#endif
{
	// 32 byte header
	uint32_t magic1;
	uint32_t magic2;

	// flags split as bitfields
	bool not_main_flash : 1;
	uint16_t dummy1 : 11;
	bool file_container : 1;
	bool has_family_id : 1;
	bool has_md5 : 1;
	bool has_tags : 1;
	uint16_t dummy2 : 16;

	uint32_t addr;
	uint32_t len;
	uint32_t block_seq;
	uint32_t block_count;
	uint32_t file_size; // or familyID;
	uint8_t data[476];
	uint32_t magic3;
} uf2_block_t;

typedef struct {
	uint32_t seq;		// current block sequence number
	uint32_t family_id; // expected family ID
	uint32_t written;	// actual written data length, in bytes

	bool is_format_ok; // whether a compatible format tag has been found
	bool is_part_set;  // whether OTA_PART_INFO has been found

	uint8_t *binpatch;	  // current block's binpatch (if any) -> pointer inside block->data
	uint8_t binpatch_len; // binpatch length

	uint8_t scheme_byte;  // byte within OTA_PART_INFO containing the target partition index
	uint8_t scheme_shift; // bit shift (>>) of the partition index byte
	bool scheme_binpatch; // whether binpatch should be applied (= scheme is OTA2)

	uint32_t erased_offset; // offset of region erased during update
	uint32_t erased_length; // length of erased region

	struct fal_partition *part_table;  // partition table
	uint32_t part_table_len;		   // partition count
	bool part_table_copied;			   // whether partition table is dynamically allocated
	const struct fal_partition *part;  // target partition for the current scheme
	const struct fal_flash_dev *flash; // flash device structure of the target partition
} uf2_ota_t;

typedef struct {
	char *fw_name;
	char *fw_version;
	char *lt_version;
	char *board;
} uf2_info_t;

typedef enum {
	UF2_TAG_VERSION	  = 0x9FC7BC, // version of firmware file - UTF8 semver string
	UF2_TAG_PAGE_SIZE = 0x0BE9F7, // page size of target device (32 bit unsigned number)
	UF2_TAG_SHA2	  = 0xB46DB0, // SHA-2 checksum of firmware (can be of various size)
	UF2_TAG_DEVICE	  = 0x650D9D, // description of device (UTF8)
	UF2_TAG_DEVICE_ID = 0xC8A729, // device type identifier
	// format versions
	UF2_TAG_OTA_FORMAT_1 = 0x5D57D0,
	UF2_TAG_OTA_FORMAT_2 = 0x6C8492,
	// LibreTiny custom tags
	UF2_TAG_OTA_PART_LIST = 0x6EC68A, // list of OTA schemes this package is usable in
	UF2_TAG_OTA_PART_INFO = 0xC0EE0C, // partition names for each target type
	UF2_TAG_BOARD		  = 0xCA25C8, // board name (lowercase code)
	UF2_TAG_FIRMWARE	  = 0x00DE43, // firmware description / name
	UF2_TAG_BUILD_DATE	  = 0x822F30, // build date/time as Unix timestamp
	UF2_TAG_BINPATCH	  = 0xB948DE, // binary patch to convert OTA1->OTA2
	UF2_TAG_FAL_PTABLE	  = 0x8288ED, // FAL partition table length (stored in block padding)
	UF2_TAG_LT_VERSION	  = 0x59563D, // LT version (semver)
} uf2_tag_type_t;

typedef enum {
	UF2_OPC_DIFF32 = 0xFE,
} uf2_opcode_t;

typedef enum {
	UF2_SCHEME_DEVICE_SINGLE  = 0,
	UF2_SCHEME_DEVICE_DUAL_1  = 1,
	UF2_SCHEME_DEVICE_DUAL_2  = 2,
	UF2_SCHEME_FLASHER_SINGLE = 3,
	UF2_SCHEME_FLASHER_DUAL_1 = 4,
	UF2_SCHEME_FLASHER_DUAL_2 = 5,
} uf2_ota_scheme_t;

typedef enum {
	UF2_ERR_OK			  = 0,
	UF2_ERR_IGNORE		  = 1,	// block should be ignored
	UF2_ERR_MAGIC		  = 2,	// wrong magic numbers
	UF2_ERR_FAMILY		  = 3,	// family ID mismatched
	UF2_ERR_NOT_HEADER	  = 4,	// block is not a header
	UF2_ERR_OTA_VER		  = 5,	// unknown/invalid OTA format version
	UF2_ERR_OTA_WRONG	  = 6,	// no data for current OTA scheme
	UF2_ERR_PART_404	  = 7,	// no partition with that name
	UF2_ERR_PART_INVALID  = 8,	// invalid partition info tag
	UF2_ERR_PART_UNSET	  = 9,	// image broken - attempted to write without target partition
	UF2_ERR_DATA_TOO_LONG = 10, // data too long - tags won't fit
	UF2_ERR_SEQ_MISMATCH  = 11, // sequence number mismatched
	UF2_ERR_ERASE_FAILED  = 12, // erasing flash failed
	UF2_ERR_WRITE_FAILED  = 13, // writing to flash failed
	UF2_ERR_WRITE_LENGTH  = 14, // wrote fewer data than requested
} uf2_err_t;

// compatibility macros
#define UF2_ERR_PART_ONE UF2_ERR_PART_INVALID

/* Copyright (c) Kuba Szczodrzyński 2022-05-29. */

#include "uf2priv.h"

uf2_err_t uf2_parse_block(uf2_ota_t *ctx, uf2_block_t *block, uf2_info_t *info) {
	if (block->block_seq != ctx->seq)
		// sequence number must match
		return UF2_ERR_SEQ_MISMATCH;
	ctx->seq++;			   // increment sequence number after checking it
	ctx->binpatch_len = 0; // binpatch applies to one block only

	if (!block->has_tags)
		// no tags in this block, no further processing needed
		return UF2_ERR_OK;

	if (block->len > (476 - 4 - 4))
		// at least one tag + last tag must fit
		return UF2_ERR_DATA_TOO_LONG;

	uint8_t *tags_pos = block->data + block->len;
	uint8_t *tags_end = tags_pos + 476 - block->len;
	if (block->has_md5)
		tags_end -= 24;

	while (tags_pos < tags_end) {
		uf2_tag_type_t type;
		uint8_t len = uf2_read_tag(tags_pos, &type);
		if (!len)
			break;
		// skip tag header
		uint8_t *tag	= tags_pos + 4;
		uint8_t tag_len = len - 4;

		char **str_dest = NULL; // char* to copy the tag into
		uf2_err_t err	= UF2_ERR_OK;

		switch (type) {
			case UF2_TAG_FIRMWARE:
				if (info)
					str_dest = &(info->fw_name);
				break;
			case UF2_TAG_VERSION:
				if (info)
					str_dest = &(info->fw_version);
				break;
			case UF2_TAG_LT_VERSION:
				if (info)
					str_dest = &(info->lt_version);
				break;
			case UF2_TAG_BOARD:
				if (info)
					str_dest = &(info->board);
				break;

			case UF2_TAG_OTA_FORMAT_2:
				ctx->is_format_ok = true;
				break;
			case UF2_TAG_OTA_PART_LIST:
				err = uf2_parse_part_list(ctx, tag, tag_len);
				break;
			case UF2_TAG_OTA_PART_INFO:
				err = uf2_parse_part_info(ctx, tag, tag_len);
				break;
			case UF2_TAG_BINPATCH:
				ctx->binpatch	  = tag;
				ctx->binpatch_len = tag_len;
				break;
			case UF2_TAG_FAL_PTABLE:
				ctx->part_table		   = malloc(tag_len);
				ctx->part_table_len	   = tag_len / sizeof(struct fal_partition);
				ctx->part_table_copied = true;
				memcpy(ctx->part_table, tag, tag_len);
				break;
			default:
				break;
		}

		if (err != UF2_ERR_OK)
			return err;

		if (str_dest) {
			*str_dest = calloc(tag_len + 1, 1);
			memcpy(*str_dest, tag, tag_len);
		}
		// align position to 4 bytes
		tags_pos += (((len - 1) / 4) + 1) * 4;
	}

	return UF2_ERR_OK;
}

uint8_t uf2_read_tag(const uint8_t *data, uf2_tag_type_t *type) {
	uint8_t len = data[0];
	if (!len)
		return 0;
	uint32_t tag_type = data[1] | (data[2] << 8) | (data[3] << 16);
	if (!tag_type)
		return 0;
	*type = tag_type;
	return len;
}

uf2_err_t uf2_parse_part_list(uf2_ota_t *ctx, const uint8_t *tag, uint8_t tag_len) {
	if (tag_len < 3)
		return UF2_ERR_OTA_WRONG;
	uint8_t has_data = tag[ctx->scheme_byte] >> ctx->scheme_shift;
	if (has_data == 0)
		return UF2_ERR_OTA_WRONG;
	return UF2_ERR_OK;
}

uf2_err_t uf2_parse_part_info(uf2_ota_t *ctx, const uint8_t *tag, uint8_t tag_len) {
	// reset the target partition
	ctx->part = NULL;
	// reset offsets as they probably don't apply to this partition
	ctx->erased_offset = 0;
	ctx->erased_length = 0;
	// indicate that OTA_PART_INFO has been parsed
	ctx->is_part_set = true;

	if (tag_len < 3)
		return UF2_ERR_PART_INVALID;

	uint8_t index = tag[ctx->scheme_byte] >> ctx->scheme_shift;
	if (index == 0)
		return UF2_ERR_OK;
	if (index > 6)
		return UF2_ERR_PART_INVALID;

	char *part_name = (char *)tag + 3;
	char *tag_end	= (char *)tag + tag_len;

	uint8_t current_index = 0;
	while (tag_end > part_name) {
		char *part_end = memchr(part_name, '\0', tag_end - part_name);
		if (!part_end || part_name == part_end)
			return UF2_ERR_PART_INVALID;
		current_index++;
		if (current_index == index && part_end < tag_end)
			break;
		part_name = part_end + 1;
	}
	if (current_index != index)
		return UF2_ERR_PART_INVALID;

	ctx->part = NULL;
	for (uint32_t i = 0; i < ctx->part_table_len; i++) {
		if (strcmp(part_name, ctx->part_table[i].name) == 0) {
			ctx->part = ctx->part_table + i;
			break;
		}
	}

	if (!ctx->part)
		return UF2_ERR_PART_404;

	ctx->flash = fal_flash_device_find(ctx->part->flash_name);

	return UF2_ERR_OK;
}

bool uf2_is_erased(uf2_ota_t *ctx, uint32_t offset, uint32_t length) {
	uint32_t erased_end = ctx->erased_offset + ctx->erased_length;
	uint32_t end		= offset + length;
	return (offset >= ctx->erased_offset) && (end <= erased_end);
}

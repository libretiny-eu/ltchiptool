/* Copyright (c) Kuba Szczodrzyński 2022-05-29. */

#include "uf2priv.h"

uf2_ota_t *uf2_ctx_init(uf2_ota_scheme_t scheme, uint32_t family_id) {
	uf2_ota_t *ctx = calloc(1, sizeof(uf2_ota_t));
	ctx->family_id = family_id;

	ctx->scheme_byte	 = scheme >> 1;
	ctx->scheme_shift	 = (scheme & 1 ^ 1) * 4;
	ctx->scheme_binpatch = scheme == UF2_SCHEME_DEVICE_DUAL_2 || scheme == UF2_SCHEME_FLASHER_DUAL_2;

	ctx->part_table = (struct fal_partition *)fal_get_partition_table((size_t *)&ctx->part_table_len);

	return ctx;
}

uf2_info_t *uf2_info_init() {
	uf2_info_t *info = calloc(1, sizeof(uf2_info_t));
	return info;
}

void uf2_ctx_free(uf2_ota_t *ctx) {
	if (!ctx)
		return;
	if (ctx->part_table_copied)
		free(ctx->part_table);
	free(ctx);
}

void uf2_info_free(uf2_info_t *info) {
	if (!info)
		return;
	free(info->fw_name);
	free(info->fw_version);
	free(info->lt_version);
	free(info->board);
	free(info);
}

uf2_err_t uf2_check_block(uf2_ota_t *ctx, uf2_block_t *block) {
	if (block->magic1 != UF2_MAGIC_1)
		return UF2_ERR_MAGIC;
	if (block->magic2 != UF2_MAGIC_2)
		return UF2_ERR_MAGIC;
	if (block->magic3 != UF2_MAGIC_3)
		return UF2_ERR_MAGIC;
	if (block->file_container)
		// ignore file containers, for now
		return UF2_ERR_IGNORE;
	if (!block->has_family_id || block->file_size != ctx->family_id)
		// require family_id
		return UF2_ERR_FAMILY;
	return UF2_ERR_OK;
}

uf2_err_t uf2_parse_header(uf2_ota_t *ctx, uf2_block_t *block, uf2_info_t *info) {
	if (!block->has_tags || block->file_container || block->len)
		// header must have tags and no data
		return UF2_ERR_NOT_HEADER;

	uf2_err_t err = uf2_parse_block(ctx, block, info);
	if (err)
		return err;
	if (!ctx->is_format_ok)
		return UF2_ERR_OTA_VER;
	return UF2_ERR_OK;
}

uf2_err_t uf2_write(uf2_ota_t *ctx, uf2_block_t *block) {
	if (ctx->seq == 0)
		return uf2_parse_header(ctx, block, NULL);
	uf2_err_t err = uf2_parse_block(ctx, block, NULL);
	if (err)
		return err;

	if (block->not_main_flash || !block->len)
		// ignore blocks not meant for flashing
		return UF2_ERR_IGNORE;

	if (!ctx->is_part_set)
		// missing OTA_PART_INFO tag
		return UF2_ERR_PART_UNSET;

	const struct fal_partition *part  = ctx->part;
	const struct fal_flash_dev *flash = ctx->flash;
	if (!part || !flash)
		// this block is not for current OTA scheme
		return UF2_ERR_IGNORE;

	if (ctx->scheme_binpatch && ctx->binpatch_len) {
		// apply binpatch
		err = uf2_binpatch(block->data, ctx->binpatch, ctx->binpatch_len);
		if (err)
			return err;
	}

	// check writing length
	if (block->addr + block->len > part->len)
		return UF2_ERR_WRITE_FAILED;
	uint32_t offset = part->offset + block->addr;

	int ret;
	// erase sectors if needed
	if (!uf2_is_erased(ctx, offset, block->len)) {
		ret = flash->ops.erase(offset, block->len);
		if (ret < 0)
			return UF2_ERR_ERASE_FAILED;
		ctx->erased_offset = offset;
		ctx->erased_length = ret;
	}

	// write data to flash
	ret = flash->ops.write(offset, block->data, block->len);
	if (ret < 0)
		return UF2_ERR_WRITE_FAILED;
	if (ret != block->len)
		return UF2_ERR_WRITE_LENGTH;

	ctx->written += ret;
	return UF2_ERR_OK;
}

/* Copyright (c) Kuba Szczodrzyński 2022-05-28. */

#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#include "uf2binpatch.h"
#include "uf2types.h"

#include <fal.h>

/**
 * @brief Parse a block and extract information from tags.
 *
 * @param ctx context
 * @param block block to parse
 * @param info structure to write firmware info, NULL if not used
 * @return uf2_err_t error code
 */
uf2_err_t uf2_parse_block(uf2_ota_t *ctx, uf2_block_t *block, uf2_info_t *info);

/**
 * @brief Parse a tag.
 *
 * @param data pointer to tag header beginning
 * @param type [out] parsed tag type
 * @return uint8_t parsed tag length (incl. header); 0 if invalid/last tag
 */
uint8_t uf2_read_tag(const uint8_t *data, uf2_tag_type_t *type);

/**
 * @brief Parse OTA_PART_LIST tag to ensure the UF2 package is usable in this OTA scheme.
 *
 * @param ctx context
 * @param tag OTA_PART_LIST tag data
 * @param tag_len length of the tag data
 * @return uf2_err_t error code
 */
uf2_err_t uf2_parse_part_list(uf2_ota_t *ctx, const uint8_t *tag, uint8_t tag_len);

/**
 * @brief Parse OTA_PART_INFO tag to update the target partition.
 *
 * @param ctx context
 * @param tag OTA_PART_INFO tag data
 * @param tag_len length of the tag data
 * @return uf2_err_t error code
 */
uf2_err_t uf2_parse_part_info(uf2_ota_t *ctx, const uint8_t *tag, uint8_t tag_len);

/**
 * Check if specified flash memory region has already been erased during update.
 *
 * @param ctx context
 * @param offset offset to check
 * @param length length to check
 * @return bool true/false
 */
bool uf2_is_erased(uf2_ota_t *ctx, uint32_t offset, uint32_t length);

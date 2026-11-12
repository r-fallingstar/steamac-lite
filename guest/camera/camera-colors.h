#ifndef STEAMAC_CAMERA_COLORS_H
#define STEAMAC_CAMERA_COLORS_H
#include <stddef.h>
#include <stdint.h>

static inline uint8_t camera_clip(int value) {
    return value < 0 ? 0 : value > 255 ? 255 : (uint8_t)value;
}

/* Packed NV12, video range BT.601, to top-down packed BGR24 for Wine/qcap.
 * Dimensions are positive and even; each chroma pair covers a 2x2 block. */
static inline void camera_nv12_to_bgr24_scaled(const uint8_t *nv12, uint8_t *bgr, unsigned width, unsigned height,
                                             unsigned output_width, unsigned output_height) {
    const uint8_t *uv = nv12 + (size_t)width * height;
    for (unsigned row = 0; row < output_height; row++) {
        for (unsigned col = 0; col < output_width; col++) {
            unsigned source_row = row * height / output_height, source_col = col * width / output_width;
            size_t source = (size_t)source_row * width + source_col;
            size_t pixel = (size_t)row * output_width + col;
            size_t chroma = (size_t)(source_row / 2) * width + (source_col & ~1u);
            int luma = nv12[source];
            if (width == 2 * output_width && height == 2 * output_height)
                luma = (nv12[source] + nv12[source + 1] + nv12[source + width] + nv12[source + width + 1] + 2) / 4;
            int y = luma - 16;
            int u = (int)uv[chroma] - 128, v = (int)uv[chroma + 1] - 128;
            bgr[pixel * 3] = camera_clip((298 * y + 516 * u + 128) >> 8);
            bgr[pixel * 3 + 1] = camera_clip((298 * y - 100 * u - 208 * v + 128) >> 8);
            bgr[pixel * 3 + 2] = camera_clip((298 * y + 409 * v + 128) >> 8);
        }
    }
}
static inline void camera_nv12_to_bgr24(const uint8_t *nv12, uint8_t *bgr, unsigned width, unsigned height) {
    camera_nv12_to_bgr24_scaled(nv12,bgr,width,height,width,height);
}
#endif

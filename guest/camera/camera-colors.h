#ifndef STEAMAC_CAMERA_COLORS_H
#define STEAMAC_CAMERA_COLORS_H
#include <stddef.h>
#include <stdint.h>

static uint8_t camera_clip(int value) {
    return value < 0 ? 0 : value > 255 ? 255 : (uint8_t)value;
}

/* Packed NV12, video range BT.601, to top-down packed BGR24 for Wine/qcap.
 * Dimensions are positive and even; each chroma pair covers a 2x2 block. */
static void camera_nv12_to_bgr24(const uint8_t *nv12, uint8_t *bgr, unsigned width, unsigned height) {
    const uint8_t *uv = nv12 + (size_t)width * height;
    for (unsigned row = 0; row < height; row++) {
        for (unsigned col = 0; col < width; col++) {
            size_t pixel = (size_t)row * width + col;
            size_t chroma = (size_t)(row / 2) * width + (col & ~1u);
            int y = (int)nv12[pixel] - 16;
            int u = (int)uv[chroma] - 128, v = (int)uv[chroma + 1] - 128;
            bgr[pixel * 3] = camera_clip((298 * y + 516 * u + 128) >> 8);
            bgr[pixel * 3 + 1] = camera_clip((298 * y - 100 * u - 208 * v + 128) >> 8);
            bgr[pixel * 3 + 2] = camera_clip((298 * y + 409 * v + 128) >> 8);
        }
    }
}
#endif

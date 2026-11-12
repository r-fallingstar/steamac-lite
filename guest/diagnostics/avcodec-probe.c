/* SPDX-License-Identifier: Apache-2.0
 * Read-only libavcodec initialization probe. No FFmpeg headers or game modifications.
 */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

typedef struct AVCodec AVCodec;
typedef struct AVCodecContext AVCodecContext;

int main(int argc, char **argv) {
    if (argc != 2) {
        fprintf(stderr, "usage: %s /absolute/path/to/libavcodec.so.58\n", argv[0]);
        return 64;
    }
    void *library = dlopen(argv[1], RTLD_NOW | RTLD_LOCAL);
    if (!library) { fprintf(stderr, "dlopen: %s\n", dlerror()); return 1; }
#define LOAD(type, name) type name = (type)dlsym(library, #name)
    typedef unsigned (*version_fn)(void);
    typedef const AVCodec *(*find_fn)(const char *);
    typedef AVCodecContext *(*alloc_fn)(const AVCodec *);
    typedef int (*open_fn)(AVCodecContext *, const AVCodec *, void *);
    typedef void (*free_fn)(AVCodecContext **);
    typedef int (*error_fn)(int, char *, size_t);
    LOAD(version_fn, avcodec_version);
    LOAD(find_fn, avcodec_find_decoder_by_name);
    LOAD(alloc_fn, avcodec_alloc_context3);
    LOAD(open_fn, avcodec_open2);
    LOAD(free_fn, avcodec_free_context);
    LOAD(error_fn, av_strerror);
    if (!avcodec_version || !avcodec_find_decoder_by_name || !avcodec_alloc_context3 ||
        !avcodec_open2 || !avcodec_free_context) {
        fprintf(stderr, "required libavcodec export missing\n"); dlclose(library); return 1;
    }
    unsigned version = avcodec_version();
    Dl_info info = {0};
    dladdr((void *)avcodec_version, &info);
    printf("library=%s\nversion=%u.%u.%u\n", info.dli_fname ? info.dli_fname : argv[1],
           version >> 16, (version >> 8) & 255, version & 255);
#if defined(__x86_64__)
    puts("probe_arch=x86_64");
#elif defined(__aarch64__) || defined(__arm64__)
    puts("probe_arch=arm64 (use an x86_64 build under FEX to test the reported path)");
#else
    puts("probe_arch=other");
#endif
    puts("Empty-context initialization only; success does not prove media playback.");
    const char *names[] = {"h264", "valve_h264"};
    int failed = 0, found = 0;
    for (size_t i = 0; i < sizeof names / sizeof names[0]; ++i) {
        const AVCodec *codec = avcodec_find_decoder_by_name(names[i]);
        if (!codec) { printf("%s: not found\n", names[i]); continue; }
        found++;
        AVCodecContext *context = avcodec_alloc_context3(codec);
        if (!context) { fprintf(stderr, "%s: context allocation failed\n", names[i]); failed = 1; continue; }
        int status = avcodec_open2(context, codec, NULL);
        char error[256] = {0};
        if (status < 0 && av_strerror) av_strerror(status, error, sizeof error);
        printf("%s: avcodec_open2=%d%s%s\n", names[i], status, *error ? " error=" : "", error);
        if (status < 0) failed = 1;
        avcodec_free_context(&context);
    }
    dlclose(library);
    return failed || !found;
}

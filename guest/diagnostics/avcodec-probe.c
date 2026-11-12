/* SPDX-License-Identifier: Apache-2.0
 * Read-only libavcodec initialization probe. No FFmpeg headers or game modifications.
 */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct AVCodec AVCodec;
typedef struct AVCodecContext AVCodecContext;

static void print_version(const char *label, void *symbol, unsigned version) {
    Dl_info info = {0};
    dladdr(symbol, &info);
    printf("%slibrary=%s\n%sversion=%u.%u.%u\n", label,
           info.dli_fname ? info.dli_fname : "unknown", label,
           version >> 16, (version >> 8) & 255, version & 255);
}

int main(int argc, char **argv) {
    int threads = -1, no_cpu_flags = 0, verbose = 0;
    int arg = 1;
    for (; arg < argc && strncmp(argv[arg], "--", 2) == 0; ++arg) {
        if (strncmp(argv[arg], "--threads=", 10) == 0 && threads == -1) {
            const char *number = argv[arg] + 10;
            char *end;
            errno = 0;
            long count = strtol(number, &end, 10);
            if (!*number || *end || errno || count < 0 || count > 16) goto usage;
            threads = (int)count;
        } else if (strcmp(argv[arg], "--cpu-flags=0") == 0 && !no_cpu_flags) {
            no_cpu_flags = 1;
        } else if (strcmp(argv[arg], "--verbose") == 0 && !verbose) {
            verbose = 1;
        } else goto usage;
    }
    if (arg != argc - 1) goto usage;
    /* Preserve provenance and the last attempted decoder even if library code crashes. */
    setvbuf(stdout, NULL, _IONBF, 0);
    printf("requested_library=%s\n", argv[arg]);
    void *library = dlopen(argv[arg], RTLD_NOW | RTLD_LOCAL);
    if (!library) { fprintf(stderr, "dlopen: %s\n", dlerror()); return 1; }
#define LOAD(type, name) type name = (type)dlsym(library, #name)
    typedef unsigned (*version_fn)(void);
    typedef const AVCodec *(*find_fn)(const char *);
    typedef AVCodecContext *(*alloc_fn)(const AVCodec *);
    typedef int (*open_fn)(AVCodecContext *, const AVCodec *, void *);
    typedef void (*free_fn)(AVCodecContext **);
    typedef int (*error_fn)(int, char *, size_t);
    typedef const char *(*string_fn)(void);
    typedef int (*int_fn)(void);
    typedef void (*set_int_fn)(int);
    typedef int (*option_fn)(void *, const char *, int64_t, int);
    LOAD(version_fn, avcodec_version);
    LOAD(find_fn, avcodec_find_decoder_by_name);
    LOAD(alloc_fn, avcodec_alloc_context3);
    LOAD(open_fn, avcodec_open2);
    LOAD(free_fn, avcodec_free_context);
    LOAD(error_fn, av_strerror);
    LOAD(string_fn, avcodec_configuration);
    /* dlsym on this handle searches its dependencies; do not load a second avutil. */
    LOAD(version_fn, avutil_version);
    LOAD(int_fn, av_get_cpu_flags);
    LOAD(int_fn, av_cpu_count);
    LOAD(set_int_fn, av_force_cpu_flags);
    LOAD(set_int_fn, av_log_set_level);
    LOAD(option_fn, av_opt_set_int);
    if (!avcodec_version || !avcodec_find_decoder_by_name || !avcodec_alloc_context3 ||
        !avcodec_open2 || !avcodec_free_context) {
        fprintf(stderr, "required libavcodec export missing\n"); dlclose(library); return 1;
    }
    print_version("", (void *)avcodec_version, avcodec_version());
    if (avutil_version) print_version("avutil_", (void *)avutil_version, avutil_version());
    else puts("avutil_version=unavailable");
    if (avcodec_configuration) printf("configuration=%s\n", avcodec_configuration());
    else puts("configuration=unavailable");
#if defined(__x86_64__)
    puts("probe_arch=x86_64");
#elif defined(__aarch64__) || defined(__arm64__)
    puts("probe_arch=arm64 (use an x86_64 build under FEX to test the reported path)");
#else
    puts("probe_arch=other");
#endif
    puts("Empty-context initialization only; success does not prove media playback.");
    if ((threads >= 0 && !av_opt_set_int) ||
        (no_cpu_flags && (!av_force_cpu_flags || !av_get_cpu_flags)) ||
        (verbose && !av_log_set_level)) {
        fprintf(stderr, "requested diagnostic control export missing; no decoder tested\n");
        dlclose(library);
        return 1;
    }
    if (verbose) av_log_set_level(48); /* AV_LOG_DEBUG, FFmpeg 4.3 libavutil/log.h */
    if (av_cpu_count) printf("cpu_count=%d\n", av_cpu_count());
    else puts("cpu_count=unavailable");
    if (av_get_cpu_flags) printf("cpu_flags_detected=0x%x\n", (unsigned)av_get_cpu_flags());
    else puts("cpu_flags_detected=unavailable");
    if (no_cpu_flags) av_force_cpu_flags(0); /* Affects only this probe process. */
    if (av_get_cpu_flags) printf("cpu_flags_effective=0x%x\n", (unsigned)av_get_cpu_flags());
    if (threads >= 0) printf("threads_requested=%d\n", threads);
    else puts("threads_requested=library-default");
    printf("log_level=%s\n", verbose ? "debug" : "library-default");
    const char *names[] = {"h264", "valve_h264"};
    int failed = 0, found = 0;
    for (size_t i = 0; i < sizeof names / sizeof names[0]; ++i) {
        const AVCodec *codec = avcodec_find_decoder_by_name(names[i]);
        if (!codec) { printf("%s: not found\n", names[i]); continue; }
        found++;
        AVCodecContext *context = avcodec_alloc_context3(codec);
        if (!context) { fprintf(stderr, "%s: context allocation failed\n", names[i]); failed = 1; continue; }
        if (threads >= 0) {
            int status = av_opt_set_int(context, "threads", threads, 0);
            if (status < 0) {
                char error[256] = {0};
                if (av_strerror) av_strerror(status, error, sizeof error);
                printf("%s: set threads=%d failed=%d%s%s\n", names[i], threads,
                       status, *error ? " error=" : "", error);
                failed = 1;
                avcodec_free_context(&context);
                continue; /* Never silently test different settings than requested. */
            }
        }
        printf("%s: opening\n", names[i]);
        int status = avcodec_open2(context, codec, NULL);
        char error[256] = {0};
        if (status < 0 && av_strerror) av_strerror(status, error, sizeof error);
        printf("%s: avcodec_open2=%d%s%s\n", names[i], status, *error ? " error=" : "", error);
        if (status < 0) failed = 1;
        avcodec_free_context(&context);
    }
    dlclose(library);
    return failed || !found;

usage:
    fprintf(stderr, "usage: %s [--threads=0..16] [--cpu-flags=0] [--verbose] "
                    "/absolute/path/to/libavcodec.so.58\n", argv[0]);
    return 64;
}

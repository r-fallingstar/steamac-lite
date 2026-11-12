#!/usr/bin/env python3
"""Validate diagnostic output against disposable libraries, never Steam libraries."""
from pathlib import Path
import os
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[2]
env = dict(os.environ, DEVELOPER_DIR='/Library/Developer/CommandLineTools')
with tempfile.TemporaryDirectory(prefix='steamac-codec-test-') as temp:
    work = Path(temp).resolve()
    probe = work / 'probe'
    subprocess.run(['cc', '-Wall', '-Wextra', '-Werror', str(root / 'guest/diagnostics/avcodec-probe.c'),
                    '-o', str(probe)] + ([] if sys.platform == 'darwin' else ['-ldl']), env=env, check=True)

    def build(source, library, *extra):
        subprocess.run(['cc', '-Wall', '-Wextra', '-Werror'] +
                       (['-dynamiclib'] if sys.platform == 'darwin' else ['-shared', '-fPIC']) +
                       [str(source), '-o', str(library), *extra], env=env, check=True)

    def run(path, *options, **values):
        return subprocess.run([str(probe), *options, str(path)], capture_output=True, text=True,
                              env=dict(env, **values))

    # A separate dependency checks dlsym(handle)'s dependency lookup and avutil provenance.
    utility_source = work / 'utility.c'
    utility_source.write_text('''#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
static int cpu_flags = 0x101, log_level = 32;
unsigned avutil_version(void) { return (56u << 16) | (51u << 8) | 100u; }
int av_strerror(int n, char *s, size_t z) { (void)n; snprintf(s, z, "Invalid argument"); return 0; }
int av_get_cpu_flags(void) { return cpu_flags; }
int av_cpu_count(void) { return 8; }
void av_force_cpu_flags(int n) { cpu_flags = n; }
void av_log_set_level(int n) { log_level = n; }
int fixture_log_level(void) { return log_level; }
int av_opt_set_int(void *context, const char *name, int64_t n, int search_flags) {
    if (getenv("PROBE_FIXTURE_OPTION_ERROR") || strcmp(name, "threads") || search_flags || n < 0 || n > 16)
        return -22;
    *(int64_t *)context = n;
    return 0;
}
''')
    utility = work / ('libfixtureutil.dylib' if sys.platform == 'darwin' else 'libfixtureutil.so')
    build(utility_source, utility)
    source = work / 'fixture.c'
    source.write_text('''#include <stdint.h>
#include <stdlib.h>
#include <string.h>
int av_get_cpu_flags(void);
int fixture_log_level(void);
unsigned avcodec_version(void) { return (58u << 16) | (91u << 8) | 100u; }
const char *avcodec_configuration(void) { return "--fixture-only"; }
const void *avcodec_find_decoder_by_name(const char *s) {
    if (getenv("PROBE_FIXTURE_NO_DECODERS")) return 0;
    return s[0] == 'h' || getenv("PROBE_FIXTURE_VALVE") ? s : 0;
}
void *avcodec_alloc_context3(const void *p) {
    (void)p;
    if (getenv("PROBE_FIXTURE_ALLOC_ERROR")) return 0;
    int64_t *context = malloc(sizeof *context);
    if (context) *context = 1;
    return context;
}
int avcodec_open2(void *c, const void *p, void *d) {
    (void)d;
    const char *threads = getenv("PROBE_FIXTURE_EXPECT_THREADS");
    if (threads && *(int64_t *)c != atoi(threads)) return -22;
    if (getenv("PROBE_FIXTURE_EXPECT_NO_CPU_FLAGS") && av_get_cpu_flags() != 0) return -22;
    if (getenv("PROBE_FIXTURE_EXPECT_DEBUG") && fixture_log_level() != 48) return -22;
    /* Valve's decoder can succeed while h264 fails; failure must not be hidden. */
    return getenv("PROBE_FIXTURE_ERROR") && !strcmp(p, "h264") ? -22 : 0;
}
void avcodec_free_context(void **p) { free(*p); *p = 0; }
''')
    library = work / 'fixture.so'
    build(source, library, '-L' + str(work), '-lfixtureutil', '-Wl,-rpath,' + str(work))
    good = run(library)
    assert good.returncode == 0 and 'version=58.91.100' in good.stdout and 'h264: avcodec_open2=0' in good.stdout
    assert f'library={library}' in good.stdout.splitlines() and 'valve_h264: not found' in good.stdout
    assert f'avutil_library={utility}\n' in good.stdout and 'avutil_version=56.51.100' in good.stdout, good.stdout
    assert 'configuration=--fixture-only' in good.stdout and 'cpu_count=8' in good.stdout
    assert 'cpu_flags_effective=0x101' in good.stdout and 'threads_requested=library-default' in good.stdout
    bad = run(library, PROBE_FIXTURE_ERROR='1', PROBE_FIXTURE_VALVE='1')
    assert bad.returncode == 1 and 'avcodec_open2=-22 error=Invalid argument' in bad.stdout
    assert 'valve_h264: avcodec_open2=0' in bad.stdout
    for count in (0, 1, 2, 16):
        controlled = run(library, f'--threads={count}', '--cpu-flags=0', '--verbose',
                         PROBE_FIXTURE_EXPECT_THREADS=str(count), PROBE_FIXTURE_EXPECT_NO_CPU_FLAGS='1',
                         PROBE_FIXTURE_EXPECT_DEBUG='1', PROBE_FIXTURE_VALVE='1')
        assert controlled.returncode == 0, controlled
        assert 'cpu_flags_detected=0x101' in controlled.stdout and 'cpu_flags_effective=0x0' in controlled.stdout
        assert f'threads_requested={count}\n' in controlled.stdout and 'log_level=debug' in controlled.stdout
        assert 'valve_h264: avcodec_open2=0' in controlled.stdout
    # Overrides in one process must not affect the next invocation's defaults.
    assert run(library).stdout == good.stdout
    rejected = run(library, '--threads=2', PROBE_FIXTURE_OPTION_ERROR='1')
    assert rejected.returncode == 1 and 'set threads=2 failed=-22 error=Invalid argument' in rejected.stdout
    assert 'h264: opening' not in rejected.stdout and 'avcodec_open2=' not in rejected.stdout
    allocation = run(library, PROBE_FIXTURE_ALLOC_ERROR='1')
    assert allocation.returncode == 1 and 'context allocation failed' in allocation.stderr
    assert run(library, PROBE_FIXTURE_NO_DECODERS='1').returncode == 1
    assert run(work / 'absent.so').returncode == 1
    for option in ('--threads=-1', '--threads=17', '--threads=', '--threads=abc',
                   '--threads=99999999999999999999999', '--cpu-flags=1', '--bogus'):
        invalid = run(library, option)
        assert invalid.returncode == 64 and 'usage:' in invalid.stderr and not invalid.stdout
    assert run(library, '--threads=1', '--threads=2').returncode == 64

    # Old/custom builds without optional exports still support the original invocation.
    source.write_text('''#include <stdlib.h>
unsigned avcodec_version(void) { return (58u << 16) | (91u << 8) | 100u; }
const void *avcodec_find_decoder_by_name(const char *s) { return s[0] == 'h' ? s : 0; }
void *avcodec_alloc_context3(const void *p) { (void)p; return calloc(1, 1); }
int avcodec_open2(void *c, const void *p, void *d) { (void)c; (void)p; (void)d; return -22; }
void avcodec_free_context(void **p) { free(*p); *p = 0; }
''')
    build(source, library)
    minimal = run(library)
    assert minimal.returncode == 1 and 'h264: avcodec_open2=-22\n' in minimal.stdout
    assert 'avutil_version=unavailable' in minimal.stdout and 'configuration=unavailable' in minimal.stdout
    for option in ('--threads=1', '--cpu-flags=0', '--verbose'):
        unsupported = run(library, option)
        assert unsupported.returncode == 1 and 'diagnostic control export missing' in unsupported.stderr
        assert 'h264: opening' not in unsupported.stdout
    source.write_text('int unrelated_export(void) { return 0; }\n')
    build(source, library)
    assert 'export missing' in run(library).stderr
    print('decoder/dependency provenance, numeric errors, CPU/thread/log controls, isolation, unavailable exports: PASS')

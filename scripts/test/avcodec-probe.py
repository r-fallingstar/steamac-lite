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
    work = Path(temp)
    probe = work / 'probe'
    subprocess.run(['cc', '-Wall', '-Wextra', '-Werror', str(root / 'guest/diagnostics/avcodec-probe.c'),
                    '-o', str(probe)] + ([] if sys.platform == 'darwin' else ['-ldl']), env=env, check=True)
    source = work / 'fixture.c'
    source.write_text('''#include <stdlib.h>
#include <stdio.h>
unsigned avcodec_version(void) { return (58u << 16) | (91u << 8) | 100u; }
void *avcodec_find_decoder_by_name(const char *s) { return s[0] == 'h' ? (void *)s : 0; }
void *avcodec_alloc_context3(const void *p) { (void)p; return calloc(1, 1); }
int avcodec_open2(void *c, const void *p, void *d) {
    (void)c; (void)p; (void)d; return getenv("PROBE_FIXTURE_ERROR") ? -22 : 0;
}
void avcodec_free_context(void **p) { free(*p); *p = 0; }
int av_strerror(int n, char *s, size_t z) { (void)n; snprintf(s, z, "Invalid argument"); return 0; }
''')
    library = work / 'fixture.so'
    subprocess.run(['cc'] + (['-dynamiclib'] if sys.platform == 'darwin' else ['-shared', '-fPIC']) +
                   [str(source), '-o', str(library)], env=env, check=True)
    def run(path, **values):
        return subprocess.run([str(probe), str(path)], capture_output=True, text=True, env=dict(env, **values))
    good = run(library)
    assert good.returncode == 0 and 'version=58.91.100' in good.stdout and 'h264: avcodec_open2=0' in good.stdout
    assert str(library) in good.stdout and 'valve_h264: not found' in good.stdout
    bad = run(library, PROBE_FIXTURE_ERROR='1')
    assert bad.returncode == 1 and 'avcodec_open2=-22 error=Invalid argument' in bad.stdout
    assert run(work / 'absent.so').returncode == 1
    source.write_text('int unrelated_export(void) { return 0; }\n')
    subprocess.run(['cc'] + (['-dynamiclib'] if sys.platform == 'darwin' else ['-shared', '-fPIC']) +
                   [str(source), '-o', str(library)], env=env, check=True)
    assert 'export missing' in run(library).stderr
    print('decoder path/version, success, numeric error, missing library/export: PASS')

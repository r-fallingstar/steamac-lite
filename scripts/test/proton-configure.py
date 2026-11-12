#!/usr/bin/env python3
"""Apply the real configure patch to pinned Proton and test its UID probe with a fake engine."""
from pathlib import Path
import os
import re
import subprocess
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
PIN = re.search(r'^PROTON_COMMIT=([a-f0-9]{40})$', (ROOT/'guest/proton-vrclient/pin.env').read_text(), re.M)[1]
SOURCE = urllib.request.urlopen(f'https://raw.githubusercontent.com/ValveSoftware/Proton/{PIN}/configure.sh', timeout=30).read()
ENV = {**os.environ, 'DEVELOPER_DIR': '/Library/Developer/CommandLineTools'}

def probe(source, engine, cwd, *, uid='0', fail=False):
    text = source.decode()
    start = text.index('check_container_engine() {')
    function = text[start:text.index('\n}\n', start)+3]
    prelude = '''set -eu
cmd() { "$@"; }
stat() { :; }
info() { :; }
err() { echo "$*" >&2; }
die() { echo "$*" >&2; exit 1; }
CONTAINER_MOUNT_OPTS=""
'''
    return subprocess.run(['bash', '-c', prelude+function+'\ncheck_container_engine "$1" sdk-test\n',
                           'probe', str(engine)], cwd=cwd,
                          env={**ENV, 'TEST_PROBE_UID': uid, 'TEST_PROBE_FAIL': '1' if fail else '0'},
                          capture_output=True, text=True)

with tempfile.TemporaryDirectory(prefix='proton-configure-') as temporary:
    root = Path(temporary)
    original = root/'configure.sh'
    original.write_bytes(SOURCE)
    subprocess.run(['git', 'init', '-q', str(root)], env=ENV, check=True)
    patch = ROOT/'guest/proton-vrclient/patches/0002-configure-separate-container-diagnostics-from-UID.patch'
    subprocess.run(['git', '-C', str(root), 'apply', '--check', str(patch)], env=ENV, check=True)
    subprocess.run(['git', '-C', str(root), 'apply', str(patch)], env=ENV, check=True)
    patched = original.read_bytes()
    engine = root/'podman'
    engine.write_text('''#!/bin/sh
echo 'systemd user session unavailable; falling back to cgroupfs' >&2
if [ "$TEST_PROBE_FAIL" = 1 ]; then exit 125; fi
printf '%s\n' "$TEST_PROBE_UID"
''')
    engine.chmod(0o755)
    assert probe(SOURCE, engine, root).returncode != 0, 'original must reproduce the warning/UID failure'
    print('original pinned configure reproduces warning contamination: PASS')
    for uid in ['0', str(os.getuid())]:
        result = probe(patched, engine, root, uid=uid)
        assert result.returncode == 0, result.stderr
        assert 'systemd user session unavailable' in result.stderr
        print('numeric UID accepted while stderr warnings remain visible: PASS')
    for uid, fail in [('not-a-uid', False), ('123456789', False), ('0', True)]:
        result = probe(patched, engine, root, uid=uid, fail=fail)
        assert result.returncode != 0, (uid, fail)
        assert not (root/'permission_check').exists()
    print('non-numeric UID, unmapped owner and engine failure rejected: PASS')
    assert 'integer expression expected' not in probe(patched, engine, root, uid='not-a-uid').stderr
    subprocess.run(['bash', '-n', str(original)], check=True)
    print('pinned configure patch and shell syntax: PASS; no container started')

#!/usr/bin/env python3
"""Exercise orchestration with failing child builders and real HTTP range downloads."""
from pathlib import Path
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
import shutil
import subprocess
import tempfile
import threading
import importlib.util

repo = Path(__file__).resolve().parents[2]
env = dict(os.environ, DEVELOPER_DIR='/Library/Developer/CommandLineTools')

def run(command, cwd, **kw):
    return subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True, **kw)

with tempfile.TemporaryDirectory(prefix='steamac-build-test-') as tmp:
    root = Path(tmp)
    shutil.copy(repo / 'build.sh', root / 'build.sh')
    paths = ['host/' + name + '/build.sh' for name in ('moltenvk', 'kosmickrisp', 'libepoxy', 'virglrenderer', 'libkrun', 'launcher')]
    paths += ['guest/kernel/build.sh', 'guest/mesa/build.sh', 'scripts/build-image.sh']
    for name in paths:
        p = root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(f'#!/bin/bash\necho "{name} ${{STEAMAC_NO_BUNDLE:-0}} $*" >> steps\n' +
                     ('set -e\nfalse\necho SHOULD_NOT_RUN >> steps\n' if 'kosmickrisp' in name else ''))
        p.chmod(0o755)
    (root / 'bin').mkdir()
    sw = root / 'bin/sw_vers'; sw.write_text('#!/bin/sh\necho 27.2\n'); sw.chmod(0o755)
    env['PATH'] = str(root / 'bin') + ':' + os.environ['PATH']
    result = run(['bash', 'build.sh', 'all'], root)
    assert result.returncode == 0, result.stderr
    steps = (root / 'steps').read_text()
    assert 'SHOULD_NOT_RUN' not in steps
    assert 'host/libepoxy/build.sh' in steps and 'WARNING' in result.stderr
    assert 'host/launcher/build.sh 1 ' in steps and steps.rstrip().endswith('host/launcher/build.sh 0')
    (root / 'steps').unlink()
    env['STEAMAC_REQUIRE_KOSMICKRISP'] = '1'
    result = run(['bash', 'build.sh', 'host'], root)
    assert result.returncode != 0 and 'host/libepoxy/build.sh' not in (root / 'steps').read_text()
    del env['STEAMAC_REQUIRE_KOSMICKRISP']
    print('optional failure continues safely; strict failure stops; all finishes app after guest: PASS')

    helper = repo / 'host/launcher/bundle-status.sh'
    def bundle(**variables):
        command = '. "$1"; should_bundle "$2"'
        current = dict(env, **variables)
        return subprocess.run(['bash', '-c', command, 'test', str(helper), str(root / 'out')], env=current, capture_output=True, text=True)
    result = bundle(); assert result.returncode == 2 and 'Missing: Image initramfs.cpio.gz steamac-layer.img' in result.stderr
    assert bundle(STEAMAC_REQUIRE_BUNDLE='1').returncode == 1
    assert bundle(STEAMAC_NO_BUNDLE='1').returncode == 2
    (root / 'out').mkdir()
    for name in ('Image', 'initramfs.cpio.gz', 'steamac-layer.img'): (root / 'out' / name).touch()
    assert bundle().returncode == 0
    print('binary-only summary, strict mode and complete artifact selection: PASS')

    spec = importlib.util.spec_from_file_location('license_inputs', repo / 'host/launcher/license-inputs.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    # Probe the real tree read-only with missing commands; aggregate, do not stop at the first input.
    missing = module.missing_inputs(repo, which=lambda name: None)
    assert 'tool on PATH: go' in missing and 'tool on PATH: cargo' in missing
    # Use an empty synthetic build tree, preserving config pins and the inventory version.
    for name in ('host/launcher/licenses.sh', 'scripts/config.env', 'host/dxmt/pin.env', 'host/dxmt/build.sh'):
        target = root / name; target.parent.mkdir(parents=True, exist_ok=True); shutil.copy(repo / name, target)
    missing = module.missing_inputs(root, which=lambda name: '/bin/' + name)
    assert any('kernel/linux-' in p for p in missing) and any('dosfstools/' in p for p in missing)
    assert any('e2fsprogs/' in p for p in missing) and any('btrfs-progs/' in p for p in missing)
    assert not (root / 'work').exists()
    print('license preflight aggregates missing inputs without modifying outputs: PASS')

    content = b'steamac download fixture\n' * 4096
    ranges = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_): pass
        def do_GET(self):
            offset = int(self.headers.get('Range', 'bytes=0-').split('=')[1].split('-')[0])
            ranges.append(offset)
            self.send_response(206 if offset else 200)
            self.send_header('Content-Length', str(len(content) - offset))
            if offset: self.send_header('Content-Range', f'bytes {offset}-{len(content)-1}/{len(content)}')
            self.end_headers(); self.wfile.write(content[offset:])
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    try:
        dest = root / 'archive.bin'; partial = root / 'archive.bin.part'; partial.write_bytes(content[:1024])
        script = '. "$1"; fetch_file "$2" "$3" "$4"'
        args = ['bash', '-c', script, 'test', str(repo / 'host/dxmt/download.sh'), f'http://127.0.0.1:{server.server_port}/file', hashlib.sha256(content).hexdigest(), str(dest)]
        result = run(args, root)
        assert result.returncode == 0, result.stderr
        assert dest.read_bytes() == content and not partial.exists() and ranges == [1024]
        assert 'Downloading' in result.stderr
        assert run(args, root).returncode == 0 and ranges == [1024]
        dest.unlink(); args[-2] = '0' * 64
        result = run(args, root)
        assert result.returncode != 0 and not dest.exists() and partial.exists()
        print('real HTTP resume, completed cache reuse and checksum rejection: PASS')
    finally:
        server.shutdown(); server.server_close(); thread.join()

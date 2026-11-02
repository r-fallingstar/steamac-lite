#!/usr/bin/env python3
"""Assemble Lite.6 from the verified Lite.5 release and a tested libkrun build."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
BASE_SHA256 = '66fbb06f7b8a8cd0e3ba7bf2cbbd2077a6e564e446034553763204489b4ed562'
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--base-dmg', required=True, type=Path)
args = parser.parse_args()
env = {**os.environ, 'DEVELOPER_DIR': os.environ.get('DEVELOPER_DIR', '/Library/Developer/CommandLineTools')}
def run(command, **kwargs):
    return subprocess.run(command, env=env, check=True, **kwargs)
def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, env=env, text=True).strip()
assert not subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, env=env).strip(), 'Commit source changes before assembling'
run(['git', 'diff', '--exit-code', 'b43c894b988d8606427a77cd904e950f4054ffa4', '--', 'host/launcher'], cwd=ROOT)
assert digest(args.base_dmg) == BASE_SHA256, 'Unexpected Lite.5 base image'
library = ROOT/'work/out/host/lib/libkrun.1.dylib'
audio = json.loads(library.with_name('libkrun-lite-build.json').read_text())
assert digest(library) == audio['patched_library_sha256']
assert audio['builder_paths_removed'] and audio['audio_regression_tests_passed'] >= 32
patch = ROOT/'host/libkrun/patches/0029-snd-wait-for-capture-start-and-microphone-readiness.patch'
assert digest(patch) == audio['patch_sha256']
app = ROOT/'work/out/SteamAC Lite.app'
assert not app.exists(), 'Refusing to overwrite an existing app build'
with tempfile.TemporaryDirectory(prefix='lite-audio-base-', dir=ROOT/'work') as temporary:
    mount = Path(temporary)/'mounted'
    mount.mkdir()
    run(['hdiutil', 'attach', '-quiet', '-readonly', '-nobrowse', '-noautoopen', '-mountpoint', str(mount), str(args.base_dmg.resolve())])
    try:
        base = mount/'SteamAC Lite.app'
        run(['codesign', '--verify', '--deep', '--strict', str(base)])
        info = plistlib.loads((base/'Contents/Info.plist').read_bytes())
        assert info['CFBundleIdentifier'] == 'local.ryuu.steamac-lite'
        assert info['CFBundleShortVersionString'] == '1.9.4-lite.5'
        run(['ditto', str(base), str(app)])
    finally:
        run(['hdiutil', 'detach', '-quiet', str(mount)])
resources = app/'Contents/Resources'
layer_sha = digest(resources/'steamac-layer.img')
base_launcher_sha = digest(app/'Contents/MacOS/steamac-vm')
info.update(CFBundleShortVersionString='1.9.4-lite.6', CFBundleVersion='194006', SteamacGitCommit=head[:10])
(app/'Contents/Info.plist').write_bytes(plistlib.dumps(info))
run(['ditto', str(library), str(app/'Contents/Frameworks/libkrun.1.dylib')])
(resources/'steamac-audio-fix.json').write_text(json.dumps(audio, indent=2)+'\n')
receipt = {'kind':'verified-lite-audio-update', 'base_release':'v1.9.4-lite.5',
           'base_dmg_sha256':BASE_SHA256, 'base_launcher_sha256':base_launcher_sha,
           'source_commit':head, 'working_tree_modified':False,
           'layer_sha256':layer_sha, 'libkrun_sha256':digest(library),
           'audio_patch_sha256':audio['patch_sha256']}
(resources/'steamac-lite-provenance.json').write_text(json.dumps(receipt, indent=2)+'\n')
run(['codesign', '--force', '--sign', '-', '--entitlements', str(ROOT/'host/launcher/steamac-vm.entitlements'), str(app)])
run(['codesign', '--verify', '--deep', '--strict', str(app)])
assert digest(resources/'steamac-layer.img') == layer_sha
print('Assembled:', app)

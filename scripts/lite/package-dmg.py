#!/usr/bin/env python3
"""Package a clean Lite build, verify a copied-out app, and produce SHA-256 sums."""
import hashlib
import json
import os
from pathlib import Path
import plistlib
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT/'work/out/SteamAC Lite.app'
env = {**os.environ, 'DEVELOPER_DIR': os.environ.get('DEVELOPER_DIR', '/Library/Developer/CommandLineTools')}
info = plistlib.loads((APP/'Contents/Info.plist').read_bytes())
version = info['CFBundleShortVersionString']
receipt = json.loads((APP/'Contents/Resources/steamac-lite-provenance.json').read_text())
head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, env=env, text=True).strip()
assert receipt['source_commit'] == head and not receipt['working_tree_modified'], 'Build from a clean source commit first'
assert 'SteamacBuildOut' not in info
assert info['SteamacGitCommit'] == head[:10]
audio = json.loads((APP/'Contents/Resources/steamac-audio-fix.json').read_text())
with (APP/'Contents/Frameworks/libkrun.1.dylib').open('rb') as stream:
    library_sha = hashlib.file_digest(stream, 'sha256').hexdigest()
assert library_sha == receipt['libkrun_sha256'] == audio['patched_library_sha256']
assert audio['builder_paths_removed'] and audio['audio_regression_tests_passed'] >= 32
subprocess.run(['codesign', '--verify', '--deep', '--strict', str(APP)], check=True)
out = ROOT/'work/dist'
out.mkdir(exist_ok=True)
image = out/f'SteamAC-Lite-{version}-macos-arm64.dmg'
if image.exists():
    raise SystemExit('Refusing to overwrite an existing release image: '+str(image))
with tempfile.TemporaryDirectory(prefix='lite-dmg-', dir=ROOT/'work') as tmp:
    work = Path(tmp)
    stage = work/'contents'
    stage.mkdir()
    subprocess.run(['ditto', str(APP), str(stage/'SteamAC Lite.app')], check=True)
    (stage/'Applications').symlink_to('/Applications')
    (stage/'はじめに.txt').write_text((ROOT/'docs/quick-start.ja.md').read_text())
    (stage/'LICENSE.txt').write_bytes((ROOT/'LICENSE').read_bytes())
    subprocess.run(['hdiutil', 'create', '-quiet', '-volname', 'SteamAC Lite '+version,
                    '-srcfolder', str(stage), '-fs', 'HFS+', '-format', 'UDZO', str(image)], check=True)
    subprocess.run(['hdiutil', 'verify', '-quiet', str(image)], check=True)
    mount = work/'mounted'
    mount.mkdir()
    subprocess.run(['hdiutil', 'attach', '-quiet', '-readonly', '-nobrowse', '-noautoopen',
                    '-mountpoint', str(mount), str(image)], check=True)
    try:
        assert (mount/'Applications').is_symlink() and os.readlink(mount/'Applications') == '/Applications'
        assert (mount/'はじめに.txt').is_file()
        portable = work/'copied/SteamAC Lite.app'
        subprocess.run(['ditto', str(mount/'SteamAC Lite.app'), str(portable)], check=True)
        subprocess.run(['codesign', '--verify', '--deep', '--strict', str(portable)], check=True)
        assert json.loads((portable/'Contents/Resources/steamac-lite-provenance.json').read_text()) == receipt
        test_env = {**env, 'STEAMAC_DEFAULTS_DOMAIN': 'steamac.lite.distribution-selftest'}
        for option in ['--selftest-low-memory', '--selftest-keyboard', '--selftest-language', '--selftest-l10n', '--selftest-update']:
            subprocess.run([str(portable/'Contents/MacOS/steamac-vm'), option], env=test_env, check=True)
    finally:
        subprocess.run(['hdiutil', 'detach', '-quiet', str(mount)], check=True)
digest = hashlib.file_digest(image.open('rb'), 'sha256').hexdigest()
(out/'SHA256SUMS.txt').write_text(f'{digest}  {image.name}\n')
record = {'version': version, 'source_commit': head, 'dmg': image.name, 'sha256': digest,
          'bytes': image.stat().st_size, 'signature': 'ad-hoc; not notarized',
          'dmg_integrity_verified': True, 'copied_out_signature_verified': True,
          'copied_out_profile_selftest_passed': True, 'copied_out_keyboard_selftest_passed': True}
record.update(copied_out_update_selftest_passed=True, copied_out_language_selftest_passed=True, copied_out_localization_selftest_passed=True)
record.update(libkrun_sha256=library_sha, audio_patch_sha256=audio['patch_sha256'],
              audio_regression_tests_passed=audio['audio_regression_tests_passed'], builder_paths_removed=True)
(out/'distribution-validation.json').write_text(json.dumps(record, indent=2)+'\n')
print(json.dumps(record, indent=2))

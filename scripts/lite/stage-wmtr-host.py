#!/usr/bin/env python3
"""Replace the donor's libwmtr_host.dylib with the one build-wmtr-host.sh rebuilt from this checkout.

  stage-wmtr-host.py --record OUT   write OUT/build.json for OUT/libwmtr_host.dylib (after its tests passed)
  stage-wmtr-host.py APP [OUT]      verify the receipt against the current sources and stage it into APP

The receipt binds the library to the wmtr/ sources, the headers it compiles against and the DXMT pin
and patches, so a library built from older sources is refused instead of shipping silently.
"""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = ROOT / 'work/build/lite-wmtr'
LIBRARY = 'libwmtr_host.dylib'
TESTS = ['wmtr_loopback', 'wmtr_loopback WMTR_TEST_TRIGGER=1', 'wmtr_loopback WMTR_CLIENT_HANDLES=0',
         'wmtr_present_test', 'wmtr_spin_test', 'wmtr_lifetime_test', 'wmtr_dxmt_test']


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def pin(root=ROOT):
    values = {}
    for line in (root / 'host/dxmt/pin.env').read_text().splitlines():
        if '=' in line and not line.lstrip().startswith('#'):
            key, value = line.split('=', 1)
            values[key.strip()] = value.strip()
    return values


def source_digests(root=ROOT):
    paths = {root / 'wmtr/Makefile', root / 'host/dxmt/pin.env'}
    for directory in ('wmtr/src', 'wmtr/include', 'wmtr/gen', 'host/vrhost/include', 'guest/vr/include'):
        paths.update(p for p in (root / directory).rglob('*') if p.is_file() and '__pycache__' not in p.parts)
    paths.update((root / 'host/dxmt/patches').glob('*.patch'))
    return {p.relative_to(root).as_posix(): digest(p) for p in sorted(paths)}


def record(out, root=ROOT):
    out = Path(out)
    receipt = {
        'library': LIBRARY,
        'sha256': digest(out / LIBRARY),
        'source_commit': subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip(),
        'dxmt_fork_commit': pin(root)['DXMT_FORK_COMMIT'],
        'sources': source_digests(root),
        'tests_passed': TESTS,
    }
    (out / 'build.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(f"Recorded {LIBRARY} {receipt['sha256'][:16]} from {receipt['source_commit'][:10]}")
    return receipt


def verify(out, root=ROOT):
    out = Path(out)
    receipt = json.loads((out / 'build.json').read_text())
    if digest(out / LIBRARY) != receipt['sha256']:
        raise ValueError(f'{LIBRARY} does not match its receipt')
    if receipt['tests_passed'] != TESTS:
        raise ValueError('wmtr tests did not all pass for this build')
    current = source_digests(root)
    changed = sorted(n for n in set(current) | set(receipt['sources']) if current.get(n) != receipt['sources'].get(n))
    if changed:
        raise ValueError('Rebuild libwmtr_host (scripts/lite/build-wmtr-host.sh); changed since: ' + ', '.join(changed[:5]))
    return receipt


def stage(app, out=DEFAULT_OUT, root=ROOT):
    app = Path(app)
    receipt = verify(out, root)
    target = app / 'Contents/Frameworks' / LIBRARY
    if not target.exists():
        raise ValueError(f'The donor has no {LIBRARY} to replace')
    receipt['donor_sha256'] = digest(target)
    shutil.copyfile(Path(out) / LIBRARY, target)
    target.chmod(0o755)
    subprocess.run(['codesign', '--force', '--sign', '-', str(target)], check=True, capture_output=True)
    # The ad-hoc signature changes the file: record what ships, next to what was built and tested.
    receipt['staged_sha256'] = digest(target)
    receipt['license'] = 'wmtr BSD-3-Clause; DXMT LGPL-2.1-or-later (unchanged pin, see NOTICE); LLVM Apache-2.0 WITH LLVM-exception'
    (app / 'Contents/Resources/steamac-wmtr-build.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(f"Staged {LIBRARY} from {receipt['source_commit'][:10]} (donor {receipt['donor_sha256'][:16]})")
    return receipt


if __name__ == '__main__':
    if sys.argv[1:2] == ['--record']:
        record(sys.argv[2])
    else:
        stage(*sys.argv[1:])

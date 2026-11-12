#!/usr/bin/env python3
"""Stage verified source-pinned x86 codecs for the private compatibility tool."""
import importlib.util
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / 'work/video-release/runtime'
_spec = importlib.util.spec_from_file_location('video_build_protocol',
                                              Path(__file__).with_name('record-video-build.py'))
_protocol = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_protocol)


def stage(layer, app, *, root=ROOT, runtime=None):
    runtime = INPUT if runtime is None else runtime
    # Finish all source, recipe, configuration, evidence and payload checks BEFORE
    # writing anything to the application/layer. Legacy schema-1 receipts fail.
    receipt = _protocol.verify_runtime(runtime, root)
    target = layer / 'usr/lib/steamac/camera'
    payload = target / 'proton-video'
    payload.mkdir(parents=True, exist_ok=True)
    files = {}
    for name, sha in receipt['files'].items():
        shutil.copyfile(runtime / name, payload / name)
        (payload / name).chmod(0o644)
        if _protocol.digest(payload / name) != sha:
            raise ValueError('Video payload changed while staging: ' + name)
        files['files/lib/x86_64-linux-gnu/' + name] = sha
    # Detect local edits racing the copy before publishing the guest manifest.
    _protocol.verify_runtime(runtime, root)
    (target / 'proton-video.json').write_text(json.dumps({'schema': 1, 'files': files}, sort_keys=True) + '\n')
    resources = app / 'Contents/Resources'
    resources.mkdir(parents=True, exist_ok=True)
    (resources / 'steamac-video-build.json').write_text(json.dumps(receipt, indent=2) + '\n')
    notices = resources / 'licenses/Video'
    notices.mkdir(parents=True, exist_ok=True)
    for name in _protocol.LICENSES:
        shutil.copyfile(runtime / name, notices / name)
    print('Staged verified private VRChat codecs; Steam-installed libraries are unchanged')


if __name__ == '__main__':
    stage(*map(Path, sys.argv[1:]))

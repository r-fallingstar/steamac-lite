#!/usr/bin/env python3
"""stage-wmtr-host.py: stages only a library whose receipt matches the current sources and its own bytes."""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import json
import subprocess
import tempfile

spec = spec_from_file_location('stage', Path(__file__).with_name('stage-wmtr-host.py'))
stage = module_from_spec(spec)
spec.loader.exec_module(stage)


def tree(root):
    for name, text in {'wmtr/Makefile': 'host:\n', 'wmtr/src/wmtr_host.m': 'int x;\n', 'wmtr/include/wmtr.h': '\n',
                       'wmtr/gen/gen_objects.py': '\n', 'host/vrhost/include/vrlink.h': '\n',
                       'guest/vr/include/v.h': '\n', 'host/dxmt/patches/0001-a.patch': 'p\n',
                       'host/dxmt/pin.env': '# pin\nDXMT_FORK_COMMIT=17896accb64afa6b06bf1bdbc6183f6d00a35667\n'}.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text)
    subprocess.run(['git', 'init', '-q', str(root)], check=True)
    subprocess.run(['git', '-C', str(root), '-c', 'user.name=t', '-c', 'user.email=t@localhost', 'commit', '-q',
                    '--allow-empty', '-m', 't'], check=True)


def library(path, body):
    src = path.with_suffix('.c')
    src.write_text(f'int wmtr_test_marker(void) {{ return {body}; }}\n')
    subprocess.run(['clang', '-dynamiclib', '-o', str(path), str(src)], check=True)


def expect_error(fn, words):
    try:
        fn()
    except ValueError as e:
        assert words in str(e), str(e)
        return
    raise AssertionError('accepted: ' + words)


with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)
    root, out, app = tmp / 'src', tmp / 'out', tmp / 'SteamAC Lite.app'
    tree(root)
    out.mkdir()
    library(out / stage.LIBRARY, 1)
    (app / 'Contents/Frameworks').mkdir(parents=True)
    (app / 'Contents/Resources').mkdir(parents=True)
    library(app / 'Contents/Frameworks' / stage.LIBRARY, 2)
    donor = stage.digest(app / 'Contents/Frameworks' / stage.LIBRARY)

    receipt = stage.record(out, root)
    assert receipt['dxmt_fork_commit'].startswith('17896acc') and 'wmtr/src/wmtr_host.m' in receipt['sources']

    staged = stage.stage(app, out, root)
    shipped = json.loads((app / 'Contents/Resources/steamac-wmtr-build.json').read_text())
    assert shipped['donor_sha256'] == donor and shipped['staged_sha256'] == stage.digest(app / 'Contents/Frameworks' / stage.LIBRARY)
    assert staged['sha256'] == receipt['sha256'] != donor
    subprocess.run(['codesign', '--verify', str(app / 'Contents/Frameworks' / stage.LIBRARY)], check=True)

    (root / 'wmtr/src/wmtr_host.m').write_text('int y;\n')
    expect_error(lambda: stage.stage(app, out, root), 'wmtr/src/wmtr_host.m')
    (root / 'wmtr/src/wmtr_host.m').write_text('int x;\n')
    (root / 'host/dxmt/patches/0002-b.patch').write_text('q\n')
    expect_error(lambda: stage.stage(app, out, root), 'host/dxmt/patches/0002-b.patch')
    (root / 'host/dxmt/patches/0002-b.patch').unlink()

    library(out / stage.LIBRARY, 3)
    expect_error(lambda: stage.verify(out, root), 'does not match its receipt')
    stage.record(out, root)
    receipt = json.loads((out / 'build.json').read_text())
    receipt['tests_passed'] = receipt['tests_passed'][:-1]
    (out / 'build.json').write_text(json.dumps(receipt))
    expect_error(lambda: stage.verify(out, root), 'tests did not all pass')

    stage.record(out, root)
    (app / 'Contents/Frameworks' / stage.LIBRARY).unlink()
    expect_error(lambda: stage.stage(app, out, root), 'no libwmtr_host.dylib')

print('wmtr stage: all passed')

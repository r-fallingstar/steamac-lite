#!/usr/bin/env python3
"""Exercise real Git relative submodules in disposable repositories, without a Proton download."""
from pathlib import Path
import os
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
ENV = {**os.environ, 'DEVELOPER_DIR': '/Library/Developer/CommandLineTools', 'GIT_ALLOW_PROTOCOL': 'file',
       'GIT_AUTHOR_NAME': 'Checkout Test', 'GIT_AUTHOR_EMAIL': 'checkout@example.invalid',
       'GIT_COMMITTER_NAME': 'Checkout Test', 'GIT_COMMITTER_EMAIL': 'checkout@example.invalid'}

def run(*args, cwd=None, check=True):
    return subprocess.run(list(map(str, args)), cwd=cwd, env=ENV, check=check, capture_output=True, text=True)

def git(path, *args, **kw):
    return run('git', '-C', path, *args, **kw)

def prepare(path, remote, commit, check=True):
    return run('bash', '-euc', 'source "$1"; prepare_proton_checkout "$2" "$3" "$4"',
               'test', ROOT/'guest/proton-vrclient/source.sh', path, remote, commit, check=check)

def update(path, check=True):
    return run('bash', '-euc', 'source "$1"; update_proton_submodules "$2"',
               'test', ROOT/'guest/proton-vrclient/source.sh', path, check=check)

with tempfile.TemporaryDirectory(prefix='proton-source-') as temporary:
    root = Path(temporary)
    remote = root/'remote'
    remote.mkdir()
    wine = remote/'wine'
    wine.mkdir()
    git(wine, 'init', '-q')
    (wine/'configure.ac').write_text('Wine fixture\n')
    (wine/'README').write_text('Wine readme\n')
    git(wine, 'add', '.')
    git(wine, 'commit', '-qm', 'wine')
    proton = remote/'Proton'
    proton.mkdir()
    git(proton, 'init', '-q')
    (proton/'README').write_text('Proton fixture\n')
    git(proton, 'submodule', 'add', '-q', '../wine', 'wine')
    git(proton, 'config', '-f', '.gitmodules', 'submodule.obsolete.path', 'obsolete')
    git(proton, 'config', '-f', '.gitmodules', 'submodule.obsolete.url', '../does-not-exist')
    git(proton, 'add', '.')
    git(proton, 'commit', '-qm', 'Proton with relative Wine URL')
    commit = git(proton, 'rev-parse', 'HEAD').stdout.strip()

    fresh = root/'fresh'
    prepare(fresh, proton, commit)
    git(fresh, 'submodule', 'update', '--init', '--recursive')
    assert (fresh/'wine/configure.ac').read_text() == 'Wine fixture\n'
    assert git(fresh, 'remote', 'get-url', 'origin').stdout.strip() == str(proton)
    print('fresh checkout resolves relative Wine URL: PASS')

    cached = root/'cached'
    cached.mkdir()
    git(cached, 'init', '-q')
    git(cached, 'fetch', '-q', proton, commit)
    git(cached, 'checkout', '-q', '--detach', commit)
    git(cached, 'submodule', 'init')
    assert git(cached, 'submodule', 'update', '--init', 'wine', check=False).returncode != 0
    prepare(cached, proton, commit)
    git(cached, 'submodule', 'update', '--init', '--recursive')
    assert (cached/'wine/configure.ac').exists()
    print('cached checkout with broken registered URL repaired: PASS')

    for name in ['configure.ac', 'README']:
        (cached/'wine'/name).unlink()
    git(cached, 'submodule', 'update', '--init', '--recursive')
    assert not (cached/'wine/configure.ac').exists(), 'fixture must reproduce an empty, up-to-date submodule'
    update(cached)
    assert (cached/'wine/configure.ac').read_text() == 'Wine fixture\n'
    assert not (cached/'obsolete').exists()
    print('empty initialized submodule restored; stale .gitmodules entry ignored: PASS')

    (cached/'wine/configure.ac').unlink()
    (cached/'wine/README').write_text('user modification\n')
    failed = update(cached, check=False)
    assert failed.returncode != 0 and 'missing tracked files' in failed.stderr
    assert (cached/'wine/README').read_text() == 'user modification\n'
    print('partial deletion fails before make; user modifications retained: PASS')

    (proton/'README').write_text('next revision\n')
    git(proton, 'commit', '-qam', 'next revision')
    next_commit = git(proton, 'rev-parse', 'HEAD').stdout.strip()
    (fresh/'README').write_text('local edits must remain\n')
    assert prepare(fresh, proton, next_commit, check=False).returncode != 0
    assert (fresh/'README').read_text() == 'local edits must remain\n'
    assert git(fresh, 'rev-parse', 'HEAD').stdout.strip() == commit
    print('modified checkout refused without overwriting edits: PASS')

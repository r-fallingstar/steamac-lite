#!/usr/bin/env python3
"""Report missing local license inputs together, without fetching or changing files."""
import os
from pathlib import Path
import re
import shutil
import sys


def missing_inputs(root, which=shutil.which):
    missing = []
    for tool in ('go', 'cargo', 'curl', 'git'):
        if not which(tool):
            missing.append(f'tool on PATH: {tool}')

    def file(path):
        if not (root / path).is_file():
            missing.append(str(path))

    def source(path):
        directory = root / path
        if not directory.is_dir() or not any(
            p.is_file() and re.match(r'(?i)^(LICENSE|LICENCE|COPYING|NOTICE)([.\-_].*)?$', p.name)
            for p in directory.iterdir()
        ):
            missing.append(str(path) + ' (source tree with license notices)')

    for path in ('work/build/host-libkrun/src', 'work/build/host-libkrun/src/src/rutabaga_gfx',
                 'work/build/host-virglrenderer/src', 'work/build/host-moltenvk/src',
                 'work/build/host-libepoxy/src', 'host/launcher/.build/checkouts/sentry-cocoa',
                 'host/launcher/Sources/CZstd/zstd'):
        source(path)
    file('work/build/host-libkrun/src/src/rutabaga_gfx/ffi/LICENSE')
    for name in ('SPIRV-Cross', 'Vulkan-Headers', 'SPIRV-Tools', 'cereal', 'Volk', 'SPIRV-Headers'):
        file(f'work/build/host-moltenvk/src/ExternalRevisions/{name}_repo_revision')
        path = ('work/build/host-moltenvk/SPIRV-Cross' if name == 'SPIRV-Cross' else
                'work/build/host-moltenvk/src/External/SPIRV-Tools/external/spirv-headers' if name == 'SPIRV-Headers' else
                f'work/build/host-moltenvk/src/External/{name}')
        source(path)
    for path in ('work/build/host-libkrun/src/Cargo.toml', 'guest/progress-agent/Cargo.toml',
                 'work/out/host/bin/gvproxy', 'work/out/host/bin/desync'):
        file(path)
    # Use the same pinned versions as the inventory; do not infer them from borrowed binaries.
    script = (root / 'host/launcher/licenses.sh').read_text()
    kernel = re.search(r"kernel_version = '([^']+)'", script).group(1)
    file(f'work/cache/kernel/linux-{kernel}.tar.xz')
    config = dict(re.findall(r'^([A-Z][A-Z0-9_]*)=(.*)$', (root / 'scripts/config.env').read_text(), re.M))
    for key, directory, archive in (
        ('DOSFSTOOLS', 'dosfstools', 'dosfstools-{v}.tar.gz'),
        ('E2FSPROGS', 'e2fsprogs', 'e2fsprogs-{v}.tar.xz'),
        ('BTRFSPROGS', 'btrfs-progs', 'btrfs-progs-v{v}.tar.xz'),
    ):
        version = config[key + '_VERSION']
        file(f'work/cache/{directory}/{version}/' + archive.format(v=version))
    if not which('docker'):
        file('work/out/guest-toolchain.json')
    if (root / 'work/out/host/lib/libvulkan_kosmickrisp.dylib').is_file():
        file('work/build/host-kosmickrisp/src/docs/license.rst')
    if ((root / 'work/out/host/lib/libwmtr_host.dylib').is_file() or
            (root / 'work/out/dxmt/x86_64-unix/winemetal.so').is_file()):
        pin = dict(re.findall(r'^([A-Z][A-Z0-9_]*)=(.*)$', (root / 'host/dxmt/pin.env').read_text(), re.M))
        file(f"work/cache/dxmt/dxmt-{pin['DXMT_COMMIT']}.tar.gz")
        if (root / 'work/out/dxmt/x86_64-unix/winemetal.so').is_file():
            commit = re.search(r'^DXHEADERS_COMMIT=(\w+)$', (root / 'host/dxmt/build.sh').read_text(), re.M).group(1)
            file(f'work/cache/dxmt/mingw-directx-headers-{commit}.tar.gz')
            for name in ('d3d11', 'dxgi', 'd3d10core', 'winemetal'):
                file(f'work/out/dxmt/x86_64-windows/{name}.dll')
    if (root / 'work/out/host/bin/steamac-vrhost').is_file():
        file('work/out/host/VRHOST.txt')
        info = root / 'work/out/host/VRHOST.txt'
        if info.is_file():
            match = re.search(r'^build dir: (.+)$', info.read_text(), re.M)
            if match:
                build = Path(match.group(1))
                for path in ('openssl_static-prefix/src/openssl_static/LICENSE.txt',
                             '_deps/boost_pfr-src/LICENSE_1_0.txt', '_deps/openxr_sdk-src/LICENSE'):
                    file(build / path)
            else:
                missing.append('work/out/host/VRHOST.txt (missing build dir record)')
    return missing


if __name__ == '__main__':
    root = Path(os.environ.get('STEAMAC_ROOT', Path(__file__).resolve().parents[2]))
    missing = missing_inputs(root)
    if missing:
        print('License input check failed. Missing local inputs:', file=sys.stderr)
        for item in missing:
            print('  - ' + item, file=sys.stderr)
        print('See docs/upstream/requirements-and-building.md#license-inputs. '
              'Existing app and notices have not been changed.', file=sys.stderr)
        sys.exit(1)
    print('Local license inputs present. The inventory will still validate notices and dependency graphs.')

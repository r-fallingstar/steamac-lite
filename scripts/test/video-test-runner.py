#!/usr/bin/env python3
"""Offline runner checks with synthetic ELF headers; never execute FEX or a guest."""
import argparse
from contextlib import redirect_stdout, redirect_stderr
import importlib.machinery
import importlib.util
import io
import json
from pathlib import Path
import struct
import subprocess
import tempfile
from unittest.mock import Mock, patch

source = Path(__file__).resolve().parents[2] / 'guest/diagnostics/video-test-runner'
loader = importlib.machinery.SourceFileLoader('video_runner', str(source))
spec = importlib.util.spec_from_loader(loader.name, loader)
runner = importlib.util.module_from_spec(spec)
loader.exec_module(runner)


def write_elf(path, machine, interpreter=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    header = bytearray(64)
    header[:6] = b'\x7fELF\x02\x01'
    struct.pack_into('<H', header, 18, machine)
    struct.pack_into('<Q', header, 32, 64)
    struct.pack_into('<HH', header, 54, 56, int(interpreter is not None))
    data = header
    if interpreter is not None:
        name = interpreter.encode() + b'\0'
        ph = bytearray(56)
        struct.pack_into('<I', ph, 0, 3)
        struct.pack_into('<Q', ph, 8, 120)
        struct.pack_into('<Q', ph, 32, len(name))
        data += ph + name
    path.write_bytes(data)


with tempfile.TemporaryDirectory(prefix='video-runner-test-') as temp:
    base = Path(temp).resolve()
    steam, root, probe, tool = base / 'Steam', base / 'root', base / 'probe', base / 'Steam/steamapps/common/FEX-Emu'
    library = steam / 'ubuntu12_64/libavcodec.so.58'
    write_elf(probe, 62, '/lib64/ld-linux-x86-64.so.2')
    write_elf(library, 62)
    write_elf(tool / 'FEXCompatTool', 183)
    write_elf(tool / 'usr/bin/FEX', 183)
    actual_loader = root / 'usr/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2'
    write_elf(actual_loader, 62)
    (root / 'lib64').symlink_to('/usr/lib/x86_64-linux-gnu')
    assert runner.validate(root, probe, library, tool) == actual_loader
    assert runner.rooted(root, '/../lib64/./ld-linux-x86-64.so.2') == actual_loader
    assert runner.collect(steam)['libraries'][0]['sha256']
    assert runner.collect(steam)['libraries'][1]['exists'] is False
    (steam / 'steamrt64/video').mkdir(parents=True)
    (steam / 'steamrt64/video/libavcodec.so.58').symlink_to('absent.so')
    assert runner.collect(steam)['video_links'][0]['symlink'] == 'absent.so'
    # The bad layout and wrong-architecture target are rejected before FEX starts.
    for path in (base / 'merged-usr-files', base / 'missing'):
        try:
            runner.validate(path, probe, library, tool)
            raise AssertionError('missing loader accepted')
        except ValueError as error:
            assert 'RootFS cannot resolve' in str(error)
    write_elf(probe, 183, '/lib/ld-linux-aarch64.so.1')
    try:
        runner.validate(root, probe, library, tool)
        raise AssertionError('ARM probe accepted')
    except ValueError as error:
        assert 'expected ELF machine 62' in str(error)
    probe.write_bytes(b'\xcf\xfa\xed\xfe' + b'\0' * 60)
    assert 'not ELF64' in runner.elf(probe)['error']
    write_elf(probe, 62, '/lib64/ld-linux-x86-64.so.2')
    args = argparse.Namespace(rootfs=str(root), probe=str(probe), library=str(library),
                              fex_tool=str(tool), timeout=30)
    observed = []

    def fake_popen(command, **kwargs):
        env = kwargs['env']
        assert command == [str(tool / 'FEXCompatTool'), str(probe), '--verbose', str(library)]
        assert kwargs['cwd'] == tool and kwargs['start_new_session']
        assert env['FEX_ROOTFS'] == str(root) and env['FEX_PORTABLE'] == '0'
        assert env['LD_LIBRARY_PATH'] == str(library.parent)
        assert Path(env['FEX_APP_CONFIG_LOCATION']).is_dir()
        assert json.loads(Path(env['FEX_APP_CONFIG']).read_text()) == {'Config': {}}
        assert env['DEVELOPER_DIR'] == '/Library/Developer/CommandLineTools'
        observed.append(env['XDG_CONFIG_HOME'])
        return Mock(pid=123456789, wait=Mock(return_value=0))

    with patch.object(runner.sys, 'platform', 'linux'), patch.object(runner.platform, 'machine', return_value='aarch64'), \
         patch.object(runner.os, 'geteuid', return_value=1000), patch.object(runner.subprocess, 'Popen', side_effect=fake_popen), \
         redirect_stdout(io.StringIO()):
        assert runner.run(args) == 0
    assert not Path(observed[0]).exists()
    proc = Mock(pid=123456789, wait=Mock(side_effect=[subprocess.TimeoutExpired('fixture', 30), 0]))
    with patch.object(runner.sys, 'platform', 'linux'), patch.object(runner.platform, 'machine', return_value='aarch64'), \
         patch.object(runner.os, 'geteuid', return_value=1000), patch.object(runner.subprocess, 'Popen', return_value=proc), \
         patch.object(runner.os, 'killpg') as kill, redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        assert runner.run(args) == 124
        kill.assert_called_once_with(proc.pid, runner.signal.SIGKILL)
    (root / 'loop').symlink_to('/loop')
    try:
        runner.rooted(root, '/loop')
        raise AssertionError('symlink loop accepted')
    except ValueError as error:
        assert 'symlink loop' in str(error)
print('ELF/loader validation, layout collection, isolated launch plan and bounded timeout (mocked only): PASS')

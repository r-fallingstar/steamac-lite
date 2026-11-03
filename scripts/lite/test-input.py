#!/usr/bin/env python3
"""Boot a stopped test copy, check Japanese conversion/XIM/layout, then shut down."""
import argparse
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--app', type=Path, default=ROOT/'work/out/SteamAC Lite.app')
parser.add_argument('--disk', required=True, type=Path)
parser.add_argument('--layout', choices=['us', 'jis'], default='jis')
parser.add_argument('--input-source', '--input-language', dest='input_source', choices=['auto', 'latin', 'ja', 'ko', 'zh-Hans'])
parser.add_argument('--display-language', choices=['ja', 'en', 'ko', 'zh-Hans'], default='ja')
args = parser.parse_args()
disk = args.disk.resolve(strict=True)
for domain in ['es.fxgam.steamac', 'local.ryuu.steamac-lite']:
    original = Path.home()/'Library/Application Support'/domain/'steamos.img'
    if original.exists() and os.path.samefile(disk, original):
        raise SystemExit('Use a separate stopped test copy; the installed app disk is protected.')
if subprocess.run(['lsof', '-t', str(disk)], capture_output=True, text=True).stdout.strip():
    raise SystemExit('Test disk is open; no VM started.')
work = ROOT/'work'
fsck = os.environ.get('FSCK_EROFS', str(work/'build/erofs-utils/fsck/fsck.erofs'))
mkfs = os.environ.get('MKFS_EROFS', str(work/'build/erofs-utils/mkfs/mkfs.erofs'))
label = args.layout + ('-'+args.input_source+'-'+args.display_language if args.input_source else '')
log = work/f'input-test-{label}-console.log'
result_path = work/f'input-test-{label}-result.json'
runner = '''#!/bin/bash
exec 2>&1
export XDG_RUNTIME_DIR=/run/user/1000 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus DISPLAY=:0
echo JAPANESE_INPUT_TEST_BEGIN
as_user() { setpriv --reuid=1000 --regid=1000 --init-groups env HOME=/home/steamos USER=steamos LOGNAME=steamos "$@"; }
for ((i=0;i<80;i++)); do
    if timeout 3s setpriv --reuid=1000 --regid=1000 --init-groups systemctl --user is-active --quiet steamac-keyboard-session.service; then break; fi
    if timeout 3s setpriv --reuid=1000 --regid=1000 --init-groups systemctl --user is-failed --quiet steamac-keyboard-session.service; then break; fi
    sleep 1
done
set -a
[[ ! -f /run/user/1000/steamac/input.env ]] || source /run/user/1000/steamac/input.env
set +a
sleep 2
echo JAPANESE_INPUT_TEST_ENGINE_START
timeout 45s setpriv --reuid=1000 --regid=1000 --init-groups env HOME=/home/steamos USER=steamos LOGNAME=steamos /usr/bin/python3 -u /usr/lib/steamac/japanese-input-test
code=$?
if ((code!=0)); then
    as_user journalctl --user -b --no-pager -n100 \\
        -u steamac-keyboard-setup.service -u steamac-keyboard-session.service \\
        -u ibus-gamescope.service -u 'steamac-ibus-x11@*'
fi
echo JAPANESE_INPUT_TEST_EXIT=$code
exit $code
'''
with tempfile.TemporaryDirectory(prefix='input-test-', dir=work) as tmp:
    stage = Path(tmp)
    layer = stage/'layer'
    subprocess.run([fsck, '--extract='+str(layer), '--no-preserve-owner',
                    str(args.app/'Contents/Resources/steamac-layer.img')], check=True)
    lib = layer/'usr/lib/steamac'
    (lib/'japanese-input-test').write_bytes((ROOT/'scripts/test/japanese-input-guest.py').read_bytes())
    if args.input_source:
        (lib/'cjk-input-test').write_bytes((ROOT/'scripts/test/cjk-input-guest.py').read_bytes())
        runner = runner.replace('/usr/lib/steamac/japanese-input-test', '/usr/lib/steamac/cjk-input-test')
        # Only this disposable test disk is reset. The normal app disk is refused above.
        prepare = '''#!/usr/bin/python3
import os, subprocess
from pathlib import Path
for name in ['japanese-input-v1.json', 'cjk-input-v1.json']:
    (Path.home()/'.config/steamac'/name).unlink(missing_ok=True)
for path in ['/desktop/ibus/', '/org/freedesktop/ibus/engine/hangul/']:
    subprocess.run(['dconf', 'reset', '-f', path], check=True)
'''
        (lib/'cjk-test-prepare').write_text(prepare)
        (lib/'cjk-test-prepare').chmod(0o755)
        dropin = layer/'usr/lib/systemd/user/steamac-keyboard-setup.service.d'
        dropin.mkdir(parents=True, exist_ok=True)
        (dropin/'90-test-only.conf').write_text('[Service]\nExecStartPre=/usr/lib/steamac/cjk-test-prepare\n')
    (lib/'input-test-runner').write_text(runner)
    (lib/'input-test-runner').chmod(0o755)
    units = layer/'usr/lib/systemd/system'
    (units/'steamac-input-test.service').write_text('''[Unit]
Description=SteamAC input integration test (test image only)
After=display-manager.service
[Service]
Type=oneshot
ExecStart=/usr/lib/steamac/input-test-runner
TimeoutStartSec=140
StandardOutput=journal+console
StandardError=journal+console
''')
    (units/'multi-user.target.wants/steamac-input-test.service').symlink_to('../steamac-input-test.service')
    image = stage/'input-test.img'
    subprocess.run([mkfs, '-b4096', '-zlz4hc', '--all-root', str(image), str(layer)],
                   check=True, stdout=subprocess.DEVNULL)
    cmd = [str(args.app/'Contents/MacOS/steamac-vm'), '--headless', '--no-sound', '--no-ssh',
           '--no-vr', '--no-crash-reports', '--keyboard-layout', args.layout,
           '--disk', str(disk), '--disk', str(image)+':ro']
    if args.input_source:
        cmd += ['--cmdline', 'console=hvc0 loglevel=4 rootwait virtio_snd.msg_timeout_ms=10000 '
                'steamac.vrchat_setup=0'+(' steamac.input_language='+args.input_source if args.input_source != 'auto' else ''),
                '-AppleLanguages', '('+args.display_language+')']
    test_domain = 'steamac.lite.input-source-test.'+label
    subprocess.run(['defaults', 'write', test_domain, 'applicationLanguage', '-string', args.display_language], check=True)
    test_env = {**os.environ, 'STEAMAC_DEFAULTS_DOMAIN': test_domain}
    expected_source = args.input_source
    if args.input_source == 'auto':
        probe = subprocess.check_output([str(args.app/'Contents/MacOS/steamac-vm'), '--selftest-keyboard'], env=test_env, text=True)
        expected_source = re.search(r'input-source: detected ([\w-]+)', probe)[1]
    forced = False
    started = time.monotonic()
    with log.open('w') as out:
        process = subprocess.Popen(cmd, stdout=out, stderr=subprocess.STDOUT, start_new_session=True, env=test_env)
        try:
            while time.monotonic()-started < 165:
                content = log.read_text(errors='replace')
                if 'JAPANESE_INPUT_TEST_EXIT=' in content or process.poll() is not None:
                    break
                time.sleep(1)
        finally:
            if process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=90)
            except subprocess.TimeoutExpired:
                forced = True
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            subprocess.run(['defaults', 'delete', test_domain], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    content = log.read_text(errors='replace')
    passed = 'JAPANESE_INPUT_TEST_EXIT=0' in content and not forced and process.returncode == 0
    details = re.search(r'JAPANESE_INPUT_RESULT (\{[^\r\n]*\})', content)
    result = dict(layout=args.layout, test_passed=passed, exit_code=process.returncode,
                  shutdown_forced=forced, elapsed_seconds=round(time.monotonic()-started, 1),
                  vrchat_launched=False, refresh_hz=60)
    if args.input_source and not details:
        passed = False
        result['test_passed'] = False
    if details:
        result['checks'] = json.loads(details[1])
        if args.input_source:
            passed = passed and result['checks']['detected_mac_input_source'] == expected_source
            passed = passed and result['checks']['display_language'] == args.display_language
            result['test_passed'] = passed
    result_path.write_text(json.dumps(result, indent=2, ensure_ascii=False)+'\n')
    print(json.dumps(result, ensure_ascii=False), flush=True)
    if not passed:
        print(content[-14000:])
    raise SystemExit(0 if passed else 1)

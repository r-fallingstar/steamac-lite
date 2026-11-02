#!/usr/bin/env python3
"""Exercise the actual first-run service on a separate stopped SteamOS test disk.

The test removes only VRChat's settings on the TEST copy and restores Valve's
backed-up FEX. Production disks are explicitly rejected; no SSH or game launch.
"""
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
parser.add_argument("--app", type=Path, default=ROOT/"work/out/SteamAC Lite.app")
parser.add_argument("--disk", type=Path, required=True)
parser.add_argument("--maintenance", action="store_true", help="simulate a Valve FEX update after setup completed")
args = parser.parse_args()
disk = args.disk.resolve(strict=True)
for domain in ("es.fxgam.steamac", "local.ryuu.steamac-lite"):
    original = Path.home()/"Library/Application Support"/domain/"steamos.img"
    if original.exists() and os.path.samefile(disk, original):
        raise SystemExit("Refusing a production disk; use a stopped test copy.")
if subprocess.run(["lsof", "-t", str(disk)], capture_output=True, text=True).stdout.strip():
    raise SystemExit("Test disk is open")
work = ROOT/"work"
prepare = '''#!/usr/bin/python3
import runpy, shutil
from pathlib import Path
m=runpy.run_path('/usr/lib/steamac/vrchat-setup')
state=m['STATE'];state.mkdir(parents=True,exist_ok=True)
(state/'complete.json').unlink(missing_ok=True)
local=m['account']()
if local is None:
    path=m['STEAM']/'config/loginusers.vdf'
    print('ACCOUNT_DIAGNOSTIC '+str({'loginusers_exists':path.exists(),'localconfig_count':len(list((m['STEAM']/'userdata').glob('*/config/localconfig.vdf'))),'fields':[(len(k),k[0],k[-1]) for k in m['entries'](path.read_text())[0]] if path.exists() else []}),flush=True)
assert local is not None, 'Test copy needs an existing signed-in Steam account' 
config=m['STEAM']/'config/config.vdf'
text=config.read_text()
for key in ['name','config','priority']:text=m['set_value'](text,(*m['MAPPING'],key),None)
m['atomic_write'](config,text)
m['atomic_write'](local,m['set_value'](local.read_text(),m['LAUNCH'],None))
backup=next((Path.home()/'fex-eac-work/valve-backup').glob('FEX-*'))
for name in m['validate_payload']()[0]['files']:
    shutil.copy2(backup/name,m['tool']('3127680')/name)
print('VRCHAT_SETUP_PREPARED',flush=True)
'''
monitor = '''#!/usr/bin/python3
import hashlib,json,runpy,time,subprocess
m=runpy.run_path('/usr/lib/steamac/vrchat-setup')
deadline=time.monotonic()+170
while time.monotonic()<deadline:
 if (m['STATE']/'complete.json').exists():
  target=m['tool']('3127680'); receipt=m['validate_payload']()[0]
  if target and all(hashlib.sha256((target/n).read_bytes()).hexdigest()==h for n,h in receipt['files'].items()):break
 time.sleep(1)
assert (m['STATE']/'complete.json').exists(), 'Setup completion timed out'
receipt=m['validate_payload']()[0];target=m['tool']('3127680')
local=m['account']();text=(m['STEAM']/'config/config.vdf').read_text()
result={'complete':True,'fex_files_verified':all(hashlib.sha256((target/n).read_bytes()).hexdigest()==h for n,h in receipt['files'].items()),'valve_backup_present':(m['STATE']/'valve-fex-backup/usr/bin/FEX').exists(),'vrchat_proton':m['value'](text,(*m['MAPPING'],'name')),'vrchat_options':m['compatible_launch'](m['value'](local.read_text(),m['LAUNCH'])),'vrchat_launched':False,'ssh_enabled':False}
assert result['fex_files_verified'] and result['valve_backup_present'] and result['vrchat_proton']=='proton_experimental' and result['vrchat_options']
# A second application is a no-op for FEX and retains the exact user options.
print('VRCHAT_SETUP_RESULT '+json.dumps(result),flush=True)
'''
if args.maintenance:
    start=prepare.index("(state/'complete.json').unlink(missing_ok=True)")
    end=prepare.index("backup=next(",start)
    prepare=prepare[:start]+"assert (state/'complete.json').exists(), 'Complete the first-run test first'\n"+prepare[end:]
with tempfile.TemporaryDirectory(prefix="vrchat-test-", dir=work) as tmp:
    stage = Path(tmp)
    layer = stage/"layer"
    subprocess.run([str(work/"build/erofs-utils/fsck/fsck.erofs"), "--extract="+str(layer),
                    "--no-preserve-owner", str(args.app/"Contents/Resources/steamac-layer.img")],
                   check=True, stdout=subprocess.DEVNULL)
    lib = layer/"usr/lib/steamac"
    # Include any current guest-only edits without recompiling the host.
    for relative in ["usr/lib/systemd/user/steam.service.d/70-steamac-vrchat-setup.conf"]:
        (layer/relative).write_bytes((ROOT/"guest/layer"/relative).read_bytes())
    (lib/"vrchat-setup").write_bytes((ROOT/"guest/layer/usr/lib/steamac/vrchat-setup").read_bytes())
    (lib/"vrchat-setup").chmod(0o755)
    for name, data in (("vrchat-test-prepare",prepare),("vrchat-test-monitor",monitor)):
        (lib/name).write_text(data);(lib/name).chmod(0o755)
    units = layer/"usr/lib/systemd/system"
    user = "/usr/bin/setpriv --reuid=1000 --regid=1000 --init-groups /usr/bin/env HOME=/home/steamos USER=steamos LOGNAME=steamos XDG_RUNTIME_DIR=/run/user/1000 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus"
    for phase in ("prepare", "monitor"):
        ordering = "After=local-fs.target\nBefore=display-manager.service" if phase == "prepare" else "After=display-manager.service"
        name = "steamac-vrchat-test-"+phase+".service"
        (units/name).write_text(f"[Unit]\n{ordering}\n[Service]\nType=oneshot\nExecStart={user} /usr/lib/steamac/vrchat-test-{phase}\nStandardOutput=journal+console\nStandardError=journal+console\nTimeoutStartSec=190\n")
        (units/"multi-user.target.wants"/name).symlink_to("../"+name)
    image = stage/"test.img"
    subprocess.run([str(work/"build/erofs-utils/mkfs/mkfs.erofs"), "-b4096", "-zlz4hc", "--all-root", str(image), str(layer)], check=True, stdout=subprocess.DEVNULL)
    log = work/"vrchat-setup-test-console.log"
    started = time.monotonic(); forced = False
    with log.open("w") as out:
        process = subprocess.Popen([str(args.app/"Contents/MacOS/steamac-vm"), "--headless", "--no-sound", "--no-ssh", "--no-vr", "--no-crash-reports", "--cmdline", "console=hvc0 loglevel=4 rootwait steamac.vrchat_setup=1 steamac.setup_language=ja", "--disk", str(disk), "--disk", str(image)+":ro"], stdout=out, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            while time.monotonic()-started < 205:
                content = log.read_text(errors="replace")
                if "VRCHAT_SETUP_RESULT " in content or "Setup completion timed out" in content or "ACCOUNT_DIAGNOSTIC" in content or "AssertionError" in content or process.poll() is not None:
                    break
                time.sleep(1)
        finally:
            if process.poll() is None:process.terminate()
            try:process.wait(timeout=60)
            except subprocess.TimeoutExpired:
                forced=True;os.killpg(process.pid,signal.SIGKILL);process.wait()
    content = log.read_text(errors="replace")
    match = re.search(r"VRCHAT_SETUP_RESULT (\{[^\r\n]*\})",content)
    result = json.loads(match[1]) if match else {"complete":False}
    result.update(maintenance=args.maintenance, exit_code=process.returncode, shutdown_forced=forced, elapsed_seconds=round(time.monotonic()-started,1))
    (work/"vrchat-setup-test-result.json").write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result))
    if not match or process.returncode != 0 or forced:
        # Console has no secrets added by this test; keep the full log private in work/.
        print(content[-6000:]);raise SystemExit(1)

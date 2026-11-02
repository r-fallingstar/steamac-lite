#!/usr/bin/env python3
"""Boot Lite on an existing *test copy* of a SteamOS disk; never launch a game."""
import argparse
import json
import os
import re
from pathlib import Path
import signal
import subprocess
import time

ROOT = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--app', type=Path, default=ROOT/'work/out/SteamAC Lite.app')
parser.add_argument('--disk', type=Path, default=Path.home()/'Library/Application Support/local.ryuu.steamac-lite/steamos.img')
parser.add_argument('--profile', choices=['auto', 'low-memory', 'manual'], default='auto')
args = parser.parse_args()
disk = args.disk.resolve(strict=True)
original = Path.home()/'Library/Application Support/es.fxgam.steamac/steamos.img'
if disk == original or (original.exists() and os.path.samefile(disk, original)):
    raise SystemExit('Use a stopped test copy, not the original SteamOS disk.')
if subprocess.run(['lsof', '-t', str(disk)], capture_output=True, text=True).stdout.strip():
    raise SystemExit('Test disk is already open; no VM started.')
log = ROOT/'work/lite-smoke-console.log'
result_path = ROOT/'work/lite-smoke-result.json'
command = [str(args.app/'Contents/MacOS/steamac-vm'), '--profile', args.profile, '--headless',
           '--no-sound', '--no-ssh', '--no-vr', '--no-crash-reports',
           '--disk', str(disk), '--disk', str(args.app/'Contents/Resources/steamac-layer.img')+':ro']
with log.open('w') as output:
    process = subprocess.Popen(command, stdout=output, stderr=subprocess.STDOUT,
                               env={**os.environ, 'STEAMAC_SENTRY': '0'}, start_new_session=True)
    print('Test VM started:', process.pid, flush=True)
    seen = set()
    expect_swap = False
    forced = False
    started = time.monotonic()
    try:
        while time.monotonic()-started < 180:
            text = log.read_text(errors='replace')
            expect_swap = 'steamac.low_memory=1' in text
            for key, marker in [('swap', 'low-memory-swap: active'), ('steam', 'Steam is ready')]:
                if marker in text and key not in seen:
                    seen.add(key)
                    print('Confirmed:', key, flush=True)
            required = {'swap', 'steam'} if expect_swap else {'steam'}
            if required.issubset(seen) or 'low-memory-swap: unavailable:' in text or process.poll() is not None:
                break
            time.sleep(5)
    finally:
        if process.poll() is None:
            print('Shutting down the test VM.', flush=True)
            process.terminate()
        try:
            process.wait(timeout=90)
        except subprocess.TimeoutExpired:
            forced = True
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
    memory = re.search(r'\bmem=(\d+)MiB', log.read_text(errors='replace'))
    result = {'steam_booted': 'steam' in seen, 'guest_4gib_disk_swap_active': 'swap' in seen,
              'profile': args.profile, 'disk_swap_expected': expect_swap,
              'guest_memory_mib': int(memory[1]) if memory else None, 'vrchat_launched': False, 'headless': True,
              'elapsed_seconds': round(time.monotonic()-started, 1),
              'shutdown_forced': forced, 'exit_code': process.returncode,
              'test_passed': 'steam' in seen and (not expect_swap or 'swap' in seen) and not forced and process.returncode == 0}
    result_path.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result), flush=True)
    raise SystemExit(0 if result['test_passed'] else 1)

#!/usr/bin/env python3
"""Exercise reversible clone-only selection with temporary Steam configurations."""
from pathlib import Path
import hashlib, runpy, tempfile

ROOT = Path(__file__).resolve().parents[2]
selector = runpy.run_path(str(ROOT/'guest/camera/select-proton.py'))
helpers = runpy.run_path(str(ROOT/'guest/layer/usr/lib/steamac/steam-title-defaults'))
TOOL = selector['TOOL']
select = selector['select']
original = '''"InstallConfigStore" { "Software" { "Valve" { "Steam" {
// Preserve unrelated settings and other games exactly.
"Language" "japanese" "CompatToolMapping" {
"42" { "name" "personal-tool" }
"438100" { "name" "proton_experimental" "config" "" "priority" "250" }
} } } } }'''

with tempfile.TemporaryDirectory() as directory:
    home = Path(directory)
    assert select(home,None,helpers,{}) == 'not requested'
    steam = home/'.local/share/Steam'
    config = steam/'config/config.vdf'
    config.parent.mkdir(parents=True)
    config.write_text(original)
    target = steam/'compatibilitytools.d'/TOOL
    target.mkdir(parents=True)
    (target/'.steamac-camera-verified-source').write_text(selector['ARCHIVE_SHA'])
    payload = target/'qcap-test'
    payload.write_bytes(b'verified fixture')
    hashes = {'qcap-test':hashlib.sha256(payload.read_bytes()).hexdigest()}
    assert 'selected' in select(home,'1',helpers,hashes)
    changed = config.read_text()
    assert changed.replace(TOOL,'proton_experimental') == original
    marker = home/'.config/steamac/camera-experiment/proton-selection.json'
    saved = marker.read_bytes()
    assert 'already selected' in select(home,'1',helpers,hashes)
    assert marker.read_bytes() == saved
    assert 'restored' in select(home,'0',helpers,hashes)
    assert config.read_text() == original
    payload.write_bytes(b'changed fixture')
    try:
        select(home,'1',helpers,hashes)
        raise AssertionError('unverified file accepted')
    except ValueError as error:
        assert 'mismatch' in str(error)
    assert config.read_text() == original
    payload.write_bytes(b'verified fixture')
    custom = original.replace('proton_experimental','my-custom-tool')
    config.write_text(custom)
    try:
        select(home,'1',helpers,hashes)
        raise AssertionError('custom selection replaced')
    except ValueError as error:
        assert 'user-selected' in str(error)
    assert config.read_text() == custom
    assert 'skipped' in select(home,'0',helpers,hashes)
    assert config.read_text() == custom

print('Camera Proton selection: opt-in, hash checks, unrelated settings, repeat, restore and custom-choice preservation PASS')

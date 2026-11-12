#!/usr/bin/python3
"""Select verified camera-compatible Proton only in explicitly opted-in test boots."""
from pathlib import Path
import hashlib, json, runpy, subprocess, sys

HERE = Path(__file__).resolve().parent
TOOL = 'proton-rtsp-11.0-20260609-4'
ARCHIVE_SHA = 'b52f231a116e9d0f1f9d19f4e870ff84392f35daae02391a6f79fdf9ca583415'
MAPPING = ('InstallConfigStore','Software','Valve','Steam','CompatToolMapping','438100')
FIELDS = ('name','config','priority')


def select(home, mode, helpers, hashes):
    if mode not in ('1', '0'):
        return 'not requested'
    steam = home/'.local/share/Steam'
    config = steam/'config/config.vdf'
    state = home/'.config/steamac/camera-experiment'
    marker = state/'proton-selection.json'
    values, put, write = (helpers[key] for key in ('vdf_entries','vdf_set','atomic_write'))
    text = config.read_text()
    entries = values(text)[0]
    current = {field: entries.get(tuple(x.lower() for x in (*MAPPING,field)), (None,))[0]
               for field in FIELDS}
    saved = json.loads(marker.read_text()) if marker.exists() else None
    if mode == '0':
        if not saved or current['name'] != TOOL:
            return 'restore skipped; no managed selection'
        for field in FIELDS:
            text = put(text, (*MAPPING,field), saved['previous'][field])
        write(config,text)
        return 'previous VRChat Proton restored'
    target = steam/'compatibilitytools.d'/TOOL
    if (target/'.steamac-camera-verified-source').read_text().strip() != ARCHIVE_SHA:
        raise ValueError('unverified camera Proton source')
    for relative, expected in hashes.items():
        with (target/relative).open('rb') as source:
            if hashlib.file_digest(source,'sha256').hexdigest() != expected:
                raise ValueError('camera Proton file mismatch: '+relative)
    if current['name'] == TOOL and saved:
        return 'camera Proton already selected'
    if current['name'] != 'proton_experimental':
        raise ValueError('leaving a different user-selected Proton unchanged')
    state.mkdir(parents=True,exist_ok=True)
    if not saved:
        write(state/'config-before-camera-proton.vdf',text)
        write(marker,json.dumps({'tool':TOOL,'archive_sha256':ARCHIVE_SHA,'previous':current},indent=2)+'\n')
    for field,value in (('name',TOOL),('config',''),('priority','250')):
        text = put(text,(*MAPPING,field),value)
    write(config,text)
    return 'camera-compatible Proton selected for VRChat only'


def main():
    args = Path('/proc/cmdline').read_text().split()
    mode = next((x.partition('=')[2] for x in args if x.startswith('steamac.camera_proton_rtsp=')),None)
    if mode is None:
        return
    if not Path('/dev/virtio-ports/fx.camera').exists():
        raise ValueError('camera experiment port missing')
    # ExecStartPre runs before Steam. Refuse edits if another session is active.
    if subprocess.run(['pgrep','-x','steam|wine|wineserver|FEX'],stdout=subprocess.DEVNULL).returncode == 0:
        raise ValueError('Steam or a game is still running')
    helpers = runpy.run_path(str(HERE.parent/'steam-title-defaults'))
    hashes = json.loads((HERE/'rtsp-camera-files.json').read_text())
    print('CAMERA_PROTON '+select(Path.home(),mode,helpers,hashes),flush=True)


if __name__ == '__main__':
    try:
        main()
    except (OSError,ValueError,KeyError) as error:
        print('CAMERA_PROTON_NOT_CHANGED '+str(error),file=sys.stderr)
        sys.exit(1)

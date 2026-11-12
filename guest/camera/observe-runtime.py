#!/usr/bin/python3
"""Local camera diagnostics only; read selected runtime metadata, never game memory."""
from pathlib import Path
import json, os, stat, time

KEYS = ('FEX_ROOTFS','FEX_PORTABLE','FEX_APP_CONFIG_LOCATION','FEX_APP_CONFIG',
        'STEAM_COMPAT_MACHINE_ARCHITECTURE','STEAM_COMPAT_EMULATOR','STEAM_COMPAT_GRAPHICS_PROVIDER',
        'STEAM_COMPAT_TOOL_PATHS','STEAM_COMPAT_CONTAINER_RUNTIME_PATH','WINEPREFIX','WINEDLLOVERRIDES')
seen = set()
end = time.monotonic() + 600
while time.monotonic() < end:
    for process in Path('/proc').iterdir():
        if not process.name.isdecimal():
            continue
        try:
            if process.stat().st_uid != 1000 or b'VRChat.exe' not in (process/'cmdline').read_bytes():
                continue
            pairs = (process/'environ').read_bytes().split(b'\0')
            env = dict(item.decode(errors='replace').split('=',1) for item in pairs if b'=' in item)
            maps = []
            for line in (process/'maps').read_text(errors='replace').splitlines():
                fields=line.split(maxsplit=5)
                if len(fields)==6 and any(word in fields[5].lower() for word in ('qcap','avicap','libv4l','fex','winegstreamer','mfplat')):
                    maps.append(fields[5])
            devices = []
            for number in range(10):
                path=process/'root/dev'/('video'+str(number))
                if path.exists():
                    s=path.stat();devices.append({'device':'/dev/video'+str(number),'character_device':stat.S_ISCHR(s.st_mode),'mode':oct(stat.S_IMODE(s.st_mode)),'uid':s.st_uid})
            opened = []
            for fd in (process/'fd').iterdir():
                try:
                    name=os.readlink(fd)
                    if name.startswith('/dev/video'):opened.append(name)
                except OSError:pass
            record={'pid':int(process.name),'environment':{key:env[key] for key in KEYS if key in env},
                    'camera_devices_in_namespace':devices,'open_camera_devices':sorted(set(opened)),
                    'camera_libraries':sorted(set(maps))}
            data=json.dumps(record,sort_keys=True)
            if data not in seen:
                seen.add(data);print('CAMERA_RUNTIME '+data,flush=True)
        except (OSError,ValueError):pass
    time.sleep(2)

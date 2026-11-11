#!/bin/bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
export DEVELOPER_DIR=/Library/Developer/CommandLineTools
OUT="$ROOT/work/installer"
mkdir -p "$OUT"
MODE=${1:-release}
if [[ "$MODE" == test ]]; then
    APP="$OUT/Test SteamAC Lite Installer.app"
    FLAGS=(-D INSTALLER_TESTING)
else
    APP="$OUT/Install SteamAC Lite.app"
    FLAGS=()
fi
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
# Only Apple's system frameworks and our Apache-licensed sources are linked.
swiftc -O -swift-version 5 -target arm64-apple-macosx15.5 \
    -debug-prefix-map "$ROOT=/src/steamac-lite" -file-prefix-map "$ROOT=/src/steamac-lite" \
    "${FLAGS[@]}" "$ROOT/host/launcher/Sources/steamac-vm/UpdateInstallSupport.swift" \
    "$ROOT/host/launcher/Sources/steamac-vm/InstallerCore.swift" "$ROOT/host/installer/InstallerStrings.swift" "$ROOT/host/installer/main.swift" \
    -o "$APP/Contents/MacOS/steamac-installer"
strip -S "$APP/Contents/MacOS/steamac-installer"
python3 - "$ROOT" "$APP" "$MODE" <<'PY'
from pathlib import Path
import plistlib,subprocess,sys,shutil
root,app=map(Path,sys.argv[1:3]);testing=sys.argv[3]=='test'
icon=root/'docs/media/icon.png'
if icon.is_file():shutil.copyfile(icon,app/'Contents/Resources/AppIcon.png')
info={'CFBundleIdentifier':'local.ryuu.steamac-lite.installer'+('.test' if testing else ''),'CFBundleName':'steamac Lite Installer','CFBundleDisplayName':'steamac Lite Installer','CFBundleExecutable':'steamac-installer','CFBundlePackageType':'APPL','CFBundleShortVersionString':'1.0.1','CFBundleVersion':'2','CFBundleIconFile':'AppIcon.png','LSMinimumSystemVersion':'15.5','NSHighResolutionCapable':True,'CFBundleDevelopmentRegion':'en','CFBundleLocalizations':['en','ja','ko','zh-Hans','ru'],'InstallerSourceCommit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),'InstallerTestBuild':testing}
(app/'Contents/Info.plist').write_bytes(plistlib.dumps(info))
for lang,name in {'ja':'steamac Lite インストーラー','en':'steamac Lite Installer','ko':'steamac Lite 설치 프로그램','zh-Hans':'steamac Lite 安装器','ru':'Установщик steamac Lite'}.items():
 p=app/'Contents/Resources'/f'{lang}.lproj';p.mkdir(exist_ok=True)
 (p/'InfoPlist.strings').write_text('"CFBundleDisplayName" = "'+name+'";\n')
PY
codesign --force --sign - "$APP/Contents/MacOS/steamac-installer"
codesign --force --sign - "$APP"
codesign --verify --deep --strict "$APP"
echo "$APP"

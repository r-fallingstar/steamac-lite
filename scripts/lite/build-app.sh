#!/bin/bash
# Build only the modified launcher; reuse audited, signed upstream graphics/kernel components.
# This is a development bundle, not an upstream release build or a replacement for build.sh.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
cd "$ROOT"
BASE_APP=${BASE_APP:-/Applications/FX Steam Launcher.app}
export DEVELOPER_DIR=${DEVELOPER_DIR:-/Library/Developer/CommandLineTools}
SDK=${SDK:-/Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk}
[[ -d "$SDK" ]] || SDK=$(xcrun --show-sdk-path)
WORK=$ROOT/work
OUT=$WORK/out
HOST=$OUT/host
PLIST=$WORK/lite-Info.plist
export BASE_APP PLIST
codesign --verify --deep --strict "$BASE_APP"
python3 - <<'PY'
import os, pathlib, plistlib
root = pathlib.Path(os.environ['BASE_APP'])
with (root/'Contents/Info.plist').open('rb') as f:
    p = plistlib.load(f)
if p.get('CFBundleIdentifier') != 'es.fxgam.steamac' or p.get('CFBundleShortVersionString') != '1.9.4':
    raise SystemExit('Expected the v1.9.4-eac.1 upstream donor app; see docs/8gb-profile.md')
PY

mkdir -p "$HOST/include" "$HOST/lib" "$WORK/build"
# Headers must have the same ABI as the donor libkrun (v1.19.6 plus this tag's patches).
PATCH_ID=$(cat host/libkrun/patches/*.patch | shasum -a 256 | cut -c1-16)
HEADERS=$WORK/build/libkrun-headers-$PATCH_ID
if [[ ! -f "$HEADERS/.steamac-headers-ready" ]]; then
    [[ ! -e "$HEADERS" ]] || { echo "Incomplete header tree: $HEADERS" >&2; exit 1; }
    git clone --depth 1 --branch v1.19.6 https://github.com/libkrun/libkrun.git "$HEADERS"
    [[ $(git -C "$HEADERS" rev-parse HEAD) == 227b2de6ed323fe180e02f871c5f325a90c13cc2 ]]
    for patch in "$ROOT"/host/libkrun/patches/*.patch; do git -C "$HEADERS" apply "$patch"; done
    touch "$HEADERS/.steamac-headers-ready"
fi
cp "$HEADERS"/include/libkrun*.h "$HOST/include/"
cp -a "$BASE_APP/Contents/Frameworks/." "$HOST/lib/"
ln -sfn libkrun.1.dylib "$HOST/lib/libkrun.dylib"
bash host/launcher/fetch-zstd.sh
python3 - <<'PY'
import os, pathlib, plistlib
p = plistlib.loads(pathlib.Path('host/launcher/Info.plist').read_bytes())
p.update(CFBundleIdentifier='local.ryuu.steamac-lite', CFBundleName='SteamAC Lite',
         CFBundleDisplayName='SteamAC Lite', CFBundleShortVersionString='1.9.4-lite.2',
         SteamacReleaseDefaults=True, SteamacLowMemoryDefaults=True, SteamacLiteBuild=True,
         SteamacPreferencesDomain='local.ryuu.steamac-lite')
pathlib.Path(os.environ['PLIST']).write_bytes(plistlib.dumps(p))
PY
FLAGS=(--package-path host/launcher --build-system native --sdk "$SDK" -c release -j "${JOBS:-2}"
    -Xcc "-I$HOST/include" -Xcc "-I$ROOT/host/vrhost/include"
    -Xlinker "-L$HOST/lib" -Xlinker -rpath -Xlinker "$HOST/lib"
    -Xlinker -sectcreate -Xlinker __TEXT -Xlinker __info_plist -Xlinker "$PLIST")
swift build "${FLAGS[@]}"
BIN=$(swift build "${FLAGS[@]}" --show-bin-path)/steamac-vm

# EROFS tools can be supplied by MacPorts/Homebrew, or built from upstream erofs-utils.
FSCK=${FSCK_EROFS:-$WORK/build/erofs-utils/fsck/fsck.erofs}
MKFS=${MKFS_EROFS:-$WORK/build/erofs-utils/mkfs/mkfs.erofs}
[[ -x "$FSCK" ]] || FSCK=$(command -v fsck.erofs)
[[ -x "$MKFS" ]] || MKFS=$(command -v mkfs.erofs)
STAGE=$(mktemp -d "$WORK/lite-stage.XXXXXX")
trap 'rm -rf "$STAGE"' EXIT
APP=$STAGE/SteamAC\ Lite.app
cp -a "$BASE_APP" "$APP"
cp "$BIN" "$APP/Contents/MacOS/steamac-vm"
cp "$PLIST" "$APP/Contents/Info.plist"
EXE=$APP/Contents/MacOS/steamac-vm
install_name_tool -delete_rpath "$HOST/lib" "$EXE"
install_name_tool -add_rpath @executable_path/../Frameworks "$EXE"
if otool -L "$EXE" | tail -n +2 | awk '{print $1}' | grep -Ev '^(@rpath/|/usr/lib/|/System/)' ; then
    echo 'Unexpected external launcher dependency' >&2; exit 1
fi

LAYER=$STAGE/layer
"$FSCK" --extract="$LAYER" --no-preserve-owner "$BASE_APP/Contents/Resources/steamac-layer.img"
install -m755 guest/layer/usr/lib/steamac/low-memory-swap "$LAYER/usr/lib/steamac/low-memory-swap"
install -m644 guest/layer/usr/lib/systemd/system/steamac-low-memory-swap.service "$LAYER/usr/lib/systemd/system/"
mkdir -p "$LAYER/usr/lib/systemd/system/multi-user.target.wants"
ln -s ../steamac-low-memory-swap.service "$LAYER/usr/lib/systemd/system/multi-user.target.wants/steamac-low-memory-swap.service"
for script in keyboard-setup keyboard-session ibus-launch ibus-x11-display nested-desktop; do
    install -m755 "guest/layer/usr/lib/steamac/$script" "$LAYER/usr/lib/steamac/$script"
done
for unit in steamac-keyboard-setup.service steamac-keyboard-session.service 'steamac-ibus-x11@.service' \
    gamescope-session.service.d/60-steamac-keyboard.conf ibus-gamescope.service.d/60-steamac-keyboard.conf \
    steam.service.d/60-steamac-keyboard.conf steamac-nested-desktop.service.d/60-steamac-keyboard.conf; do
    mkdir -p "$LAYER/usr/lib/systemd/user/$(dirname "$unit")"
    install -m644 "guest/layer/usr/lib/systemd/user/$unit" "$LAYER/usr/lib/systemd/user/$unit"
done
echo 'steamac-lite experimental-8gb-v2 Japanese-input physical-keyboard 60Hz' >> "$LAYER/usr/lib/steamac/layer-release"
"$MKFS" -b4096 -zlz4hc -T1767225600 --all-root -L steamac-lite \
    "$APP/Contents/Resources/steamac-layer.img.new" "$LAYER"
mv "$APP/Contents/Resources/steamac-layer.img.new" "$APP/Contents/Resources/steamac-layer.img"
"$FSCK" --extract "$APP/Contents/Resources/steamac-layer.img"
# The source-bound upstream layer receipt cannot describe our modified layer.
rm -f "$APP/Contents/Resources/steamac-layer.img.inputs.json"
python3 - "$APP" "$BASE_APP" <<'PY'
import hashlib, json, pathlib, subprocess, sys
app, donor = map(pathlib.Path, sys.argv[1:])
receipt = {'kind':'experimental-local-fork', 'base_release':'v1.9.4-eac.1',
           'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
           'working_tree_modified':bool(subprocess.check_output(['git','status','--porcelain'],text=True).strip()),
           'donor_layer_sha256':hashlib.sha256((donor/'Contents/Resources/steamac-layer.img').read_bytes()).hexdigest(),
           'layer_sha256':hashlib.sha256((app/'Contents/Resources/steamac-layer.img').read_bytes()).hexdigest()}
(app/'Contents/Resources/steamac-lite-provenance.json').write_text(json.dumps(receipt,indent=2)+'\n')
PY
codesign --force --sign - --entitlements host/launcher/steamac-vm.entitlements "$EXE"
codesign --force --sign - --entitlements host/launcher/steamac-vm.entitlements "$APP"
codesign --verify --deep --strict "$APP"
STEAMAC_DEFAULTS_DOMAIN=local.ryuu.steamac-lite.selftest "$EXE" --selftest-low-memory
STEAMAC_DEFAULTS_DOMAIN=local.ryuu.steamac-lite.selftest "$EXE" --selftest-keyboard
DEST=$OUT/SteamAC\ Lite.app
if [[ -e "$DEST" ]]; then mv "$DEST" "$OUT/SteamAC Lite.previous.$(date +%Y%m%d%H%M%S).app"; fi
mv "$APP" "$DEST"
echo "Built: $DEST"

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
REUSE_LAYER=${LITE_REUSE_LAYER:-0}
WORK=$ROOT/work
OUT=$WORK/out
HOST=$OUT/host
PLIST=$WORK/lite-Info.plist
export BASE_APP PLIST REUSE_LAYER
[[ -n ${LIBKRUN_OVERRIDE:-} ]] || { echo 'Lite requires the microphone fix. Run scripts/lite/build-audio-library.sh and set LIBKRUN_OVERRIDE.' >&2; exit 1; }
codesign --verify --deep --strict "$BASE_APP"
python3 - <<'PY'
import os, pathlib, plistlib, subprocess
root = pathlib.Path(os.environ['BASE_APP'])
with (root/'Contents/Info.plist').open('rb') as f:
    p = plistlib.load(f)
identity = (p.get('CFBundleIdentifier'), p.get('CFBundleShortVersionString'))
if identity not in [('es.fxgam.steamac', '1.9.4'), ('local.ryuu.steamac-lite', '1.9.4-lite.6'), ('local.ryuu.steamac-lite', '1.9.4-lite.7'), ('local.ryuu.steamac-lite', '1.9.4-lite.8'), ('local.ryuu.steamac-lite', '1.9.4-lite.9'), ('local.ryuu.steamac-lite', '1.9.4-lite.10')]:
    raise SystemExit('Expected the v1.9.4-eac.1 upstream donor or verified Lite.6–Lite.10 base app')
if identity[0] == 'local.ryuu.steamac-lite':
    import hashlib, json
    receipt = json.loads((root/'Contents/Resources/steamac-lite-provenance.json').read_text())
    if os.environ['REUSE_LAYER'] == '1':
        subprocess.run(['git', 'diff', '--exit-code', receipt['source_commit'], '--', 'guest/layer', 'fex-eac', 'scripts/lite/verify-fex-runtime.py'], check=True)
    for name, field in [('Resources/steamac-layer.img', 'layer_sha256'), ('Frameworks/libkrun.1.dylib', 'libkrun_sha256')]:
        assert hashlib.sha256((root/'Contents'/name).read_bytes()).hexdigest() == receipt[field], 'Lite base receipt mismatch'
PY

mkdir -p "$HOST/include" "$HOST/lib" "$WORK/build"
# Save the override before copying donor frameworks: it may live in HOST/lib.
KRUN_OVERRIDE_COPY=
if [[ -n ${LIBKRUN_OVERRIDE:-} ]]; then
    codesign --verify --strict "$LIBKRUN_OVERRIDE"
    KRUN_OVERRIDE_COPY=$(mktemp "$WORK/lite-krun.XXXXXX")
    cp "$LIBKRUN_OVERRIDE" "$KRUN_OVERRIDE_COPY"
fi
trap '[[ -z "$KRUN_OVERRIDE_COPY" ]] || rm -f "$KRUN_OVERRIDE_COPY"' EXIT
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
# A rebuilt libkrun can carry host fixes without rebuilding the graphics drivers.
if [[ -n ${LIBKRUN_OVERRIDE:-} ]]; then
    cp "$KRUN_OVERRIDE_COPY" "$HOST/lib/libkrun.1.dylib"
fi
ln -sfn libkrun.1.dylib "$HOST/lib/libkrun.dylib"
bash host/launcher/fetch-zstd.sh
python3 - <<'PY'
import os, pathlib, plistlib
import subprocess
p = plistlib.loads(pathlib.Path('host/launcher/Info.plist').read_bytes())
p.update(CFBundleIdentifier='local.ryuu.steamac-lite', CFBundleName='steamac Lite',
         CFBundleDisplayName='steamac Lite', CFBundleShortVersionString='1.9.4-lite.10',
         SteamacReleaseDefaults=True, SteamacLowMemoryDefaults=False, SteamacAdaptiveDefaults=True, SteamacLiteBuild=True,
         SteamacPreferencesDomain='local.ryuu.steamac-lite', CFBundleVersion='194010',
         SteamacGitCommit=subprocess.check_output(['git','rev-parse','--short=10','HEAD'],text=True).strip(),
         LSMinimumSystemVersion='15.5')
p.pop('SteamacBuildOut', None)
p['CFBundleLocalizations'] = ['en', 'ja', 'ko', 'ru', 'zh-Hans']
pathlib.Path(os.environ['PLIST']).write_bytes(plistlib.dumps(p))
PY
mkdir -p "$WORK/lite-stringsdata"
FLAGS=(--package-path host/launcher --build-system native --sdk "$SDK" -c release -j "${JOBS:-2}"
    -Xswiftc -emit-localized-strings -Xswiftc -emit-localized-strings-path -Xswiftc "$WORK/lite-stringsdata"
    -Xswiftc -debug-prefix-map -Xswiftc "$ROOT=/src/steamac-lite"
    -Xswiftc -file-prefix-map -Xswiftc "$ROOT=/src/steamac-lite"
    -Xcc "-I$HOST/include" -Xcc "-I$ROOT/host/vrhost/include"
    -Xlinker "-L$HOST/lib" -Xlinker -rpath -Xlinker "$HOST/lib"
    -Xlinker -sectcreate -Xlinker __TEXT -Xlinker __info_plist -Xlinker "$PLIST")
swift build "${FLAGS[@]}"
BIN=$(swift build "${FLAGS[@]}" --show-bin-path)/steamac-vm

if [[ "$REUSE_LAYER" != 1 ]]; then
# EROFS tools can be supplied by MacPorts/Homebrew, or built from upstream erofs-utils.
FSCK=${FSCK_EROFS:-$WORK/build/erofs-utils/fsck/fsck.erofs}
MKFS=${MKFS_EROFS:-$WORK/build/erofs-utils/mkfs/mkfs.erofs}
[[ -x "$FSCK" ]] || FSCK=$(command -v fsck.erofs)
[[ -x "$MKFS" ]] || MKFS=$(command -v mkfs.erofs)
fi
STAGE=$(mktemp -d "$WORK/lite-stage.XXXXXX")
trap 'rm -rf "$STAGE"; [[ -z "$KRUN_OVERRIDE_COPY" ]] || rm -f "$KRUN_OVERRIDE_COPY"' EXIT
APP=$STAGE/SteamAC\ Lite.app
cp -a "$BASE_APP" "$APP"
if [[ -n ${LIBKRUN_OVERRIDE:-} ]]; then
    cp "$HOST/lib/libkrun.1.dylib" "$APP/Contents/Frameworks/libkrun.1.dylib"
    cp "$(dirname "$LIBKRUN_OVERRIDE")/libkrun-lite-build.json" "$APP/Contents/Resources/steamac-audio-fix.json"
fi
cp "$BIN" "$APP/Contents/MacOS/steamac-vm"
cp "$PLIST" "$APP/Contents/Info.plist"
swiftc -O -debug-prefix-map "$ROOT=/src/steamac-lite" -file-prefix-map "$ROOT=/src/steamac-lite" -sdk "$SDK" host/launcher/Sources/steamac-vm/UpdateInstallSupport.swift host/launcher/updater/main.swift -o "$APP/Contents/Resources/steamac-updater"
strip -S "$APP/Contents/Resources/steamac-updater"
codesign --force --sign - "$APP/Contents/Resources/steamac-updater"
python3 host/launcher/l10n.py check --strict --stringsdata "$WORK/lite-stringsdata"
python3 host/launcher/l10n.py compile "$STAGE/localizations"
cp -a "$STAGE/localizations/." "$APP/Contents/Resources/"
EXE=$APP/Contents/MacOS/steamac-vm
# Remove linker debug records containing this builder's object-file paths before signing.
strip -S "$EXE"
install_name_tool -delete_rpath "$HOST/lib" "$EXE"
install_name_tool -add_rpath @executable_path/../Frameworks "$EXE"
if otool -L "$EXE" | tail -n +2 | awk '{print $1}' | grep -Ev '^(@rpath/|/usr/lib/|/System/)' ; then
    echo 'Unexpected external launcher dependency' >&2; exit 1
fi

if [[ "$REUSE_LAYER" != 1 ]]; then
LAYER=$STAGE/layer
"$FSCK" --extract="$LAYER" --no-preserve-owner "$BASE_APP/Contents/Resources/steamac-layer.img"
install -m755 guest/layer/usr/lib/steamac/low-memory-swap "$LAYER/usr/lib/steamac/low-memory-swap"
install -m644 guest/layer/usr/lib/systemd/system/steamac-low-memory-swap.service "$LAYER/usr/lib/systemd/system/"
mkdir -p "$LAYER/usr/lib/systemd/system/multi-user.target.wants"
ln -sfn ../steamac-low-memory-swap.service "$LAYER/usr/lib/systemd/system/multi-user.target.wants/steamac-low-memory-swap.service"
for script in keyboard-setup keyboard-session ibus-launch ibus-x11-display nested-desktop steam-language; do
    install -m755 "guest/layer/usr/lib/steamac/$script" "$LAYER/usr/lib/steamac/$script"
done
for unit in steam.service.d/40-steamac-language.conf steamac-keyboard-setup.service steamac-keyboard-session.service 'steamac-ibus-x11@.service' \
    gamescope-session.service.d/60-steamac-keyboard.conf ibus-gamescope.service.d/60-steamac-keyboard.conf \
    steam.service.d/60-steamac-keyboard.conf steamac-nested-desktop.service.d/60-steamac-keyboard.conf; do
    mkdir -p "$LAYER/usr/lib/systemd/user/$(dirname "$unit")"
    install -m644 "guest/layer/usr/lib/systemd/user/$unit" "$LAYER/usr/lib/systemd/user/$unit"
done
# Pinned, hashed FEX runtime: no build toolchain or third-party download on first run.
python3 scripts/lite/verify-fex-runtime.py
install -m755 guest/layer/usr/lib/steamac/vrchat-setup "$LAYER/usr/lib/steamac/vrchat-setup"
cp -a fex-eac/runtime "$LAYER/usr/lib/steamac/fex-eac-runtime"
mkdir -p "$APP/Contents/Resources/licenses/FEX-EAC"
cp -a fex-eac/runtime/licenses/. "$APP/Contents/Resources/licenses/FEX-EAC/"
for unit in steamac-vrchat-setup.service steam.service.d/70-steamac-vrchat-setup.conf; do
    mkdir -p "$LAYER/usr/lib/systemd/user/$(dirname "$unit")"
    install -m644 "guest/layer/usr/lib/systemd/user/$unit" "$LAYER/usr/lib/systemd/user/$unit"
done
echo 'steamac-lite v1.9.4-lite.10 adaptive-performance detected-Mac-input-source CJK-input physical-keyboard 60Hz' >> "$LAYER/usr/lib/steamac/layer-release"
"$MKFS" -b4096 -zlz4hc -T1767225600 --all-root -L steamac-lite \
    "$APP/Contents/Resources/steamac-layer.img.new" "$LAYER"
mv "$APP/Contents/Resources/steamac-layer.img.new" "$APP/Contents/Resources/steamac-layer.img"
"$FSCK" --extract "$APP/Contents/Resources/steamac-layer.img"
# The source-bound upstream layer receipt cannot describe our modified layer.
rm -f "$APP/Contents/Resources/steamac-layer.img.inputs.json"
fi
python3 - "$APP" "$BASE_APP" <<'PY'
import hashlib, json, pathlib, plistlib, subprocess, sys
app, donor = map(pathlib.Path, sys.argv[1:])
base_version = plistlib.loads((donor/'Contents/Info.plist').read_bytes())['CFBundleShortVersionString']
receipt = {'kind':'experimental-local-fork', 'base_release':'v1.9.4-eac.1' if base_version == '1.9.4' else 'v'+base_version,
           'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
           'working_tree_modified':bool(subprocess.check_output(['git','status','--porcelain'],text=True).strip()),
           'donor_layer_sha256':hashlib.sha256((donor/'Contents/Resources/steamac-layer.img').read_bytes()).hexdigest(),
           'layer_sha256':hashlib.sha256((app/'Contents/Resources/steamac-layer.img').read_bytes()).hexdigest()}
receipt['libkrun_sha256'] = hashlib.sha256((app/'Contents/Frameworks/libkrun.1.dylib').read_bytes()).hexdigest()
(app/'Contents/Resources/steamac-lite-provenance.json').write_text(json.dumps(receipt,indent=2)+'\n')
PY
codesign --force --sign - --entitlements host/launcher/steamac-vm.entitlements "$EXE"
codesign --force --sign - --entitlements host/launcher/steamac-vm.entitlements "$APP"
codesign --verify --deep --strict "$APP"
STEAMAC_DEFAULTS_DOMAIN=local.ryuu.steamac-lite.selftest "$EXE" --selftest-low-memory
STEAMAC_DEFAULTS_DOMAIN=local.ryuu.steamac-lite.selftest "$EXE" --selftest-keyboard
STEAMAC_DEFAULTS_DOMAIN=local.ryuu.steamac-lite.selftest "$EXE" --selftest-language
STEAMAC_DEFAULTS_DOMAIN=local.ryuu.steamac-lite.selftest "$EXE" --selftest-update
DEST=$OUT/SteamAC\ Lite.app
if [[ -e "$DEST" ]]; then mv "$DEST" "$OUT/SteamAC Lite.previous.$(date +%Y%m%d%H%M%S).app"; fi
mv "$APP" "$DEST"
echo "Built: $DEST"

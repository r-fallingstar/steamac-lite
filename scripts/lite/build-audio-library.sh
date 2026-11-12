#!/bin/bash
# Rebuild libkrun for Lite while reusing the installed graphics libraries.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
export DEVELOPER_DIR=${DEVELOPER_DIR:-/Library/Developer/CommandLineTools}
export MACOSX_DEPLOYMENT_TARGET=15.0
export SDKROOT=$(xcrun --show-sdk-path)
export LIBCLANG_PATH="$DEVELOPER_DIR/usr/lib"
export CARGO_PROFILE_RELEASE_STRIP=false
export RUSTUP_TOOLCHAIN=${RUSTUP_TOOLCHAIN:-1.90.0}
BASE_APP=${BASE_APP:-/Applications/SteamAC Lite.app}
PATCH_ID=$(cat "$ROOT"/host/libkrun/patches/*.patch | shasum -a256 | cut -c1-16)
WORK=${AUDIO_BUILD_DIR:-$ROOT/work/build/lite-audio-$PATCH_ID}
SRC=$WORK/libkrun
OUT=$ROOT/work/out/host/lib
mkdir -p "$WORK/lib" "$OUT"
codesign --verify --deep --strict "$BASE_APP"
if [[ ! -d "$SRC/.git" ]]; then
    git clone --depth 1 --branch v1.19.6 https://github.com/libkrun/libkrun.git "$SRC"
fi
[[ $(git -C "$SRC" rev-parse HEAD) == 227b2de6ed323fe180e02f871c5f325a90c13cc2 ]]
if [[ ! -f "$WORK/source-ready" ]]; then
    for patch in "$ROOT"/host/libkrun/patches/*.patch; do git -C "$SRC" apply "$patch"; done
    echo "$PATCH_ID" > "$WORK/source-ready"
fi
[[ $(cat "$WORK/source-ready") == "$PATCH_ID" ]]
for name in libepoxy.0.dylib libvirglrenderer.1.dylib libMoltenVK.dylib; do
    ln -sfn "$BASE_APP/Contents/Frameworks/$name" "$WORK/lib/$name"
done
ln -sfn libepoxy.0.dylib "$WORK/lib/libepoxy.dylib"
ln -sfn libvirglrenderer.1.dylib "$WORK/lib/libvirglrenderer.dylib"
# Link only the verified donor's libraries, not a different system virglrenderer.
mkdir -p "$WORK/pkgconfig"
for entry in 'epoxy:1.5.10' 'virglrenderer:1.1.0'; do
    name=${entry%%:*}; version=${entry#*:}
    cat > "$WORK/pkgconfig/$name.pc" <<EOF
Name: $name
Description: pinned steamac donor library
Version: $version
Libs: -L$WORK/lib -l$name
EOF
done
export PKG_CONFIG_PATH="$WORK/pkgconfig" PKG_CONFIG_LIBDIR="$WORK/pkgconfig"
export LIBRARY_PATH="$WORK/lib"
export RUSTFLAGS="${RUSTFLAGS:-} --remap-path-prefix=$ROOT=/src/steamac-lite"
cd "$SRC"
cp "$ROOT/host/libkrun/lite-Cargo.lock" Cargo.lock
# The launcher supplies its own kernel/initramfs and does not use the built-in init blob.
cargo build --locked --release -p libkrun --no-default-features --features gpu,blk,net,input,snd -j "${JOBS:-2}"
cargo test --locked --release -p krun-devices --features gpu,snd --lib --no-run --message-format=json -j "${JOBS:-2}" > "$WORK/test-build.jsonl"
TEST=$(python3 - "$WORK/test-build.jsonl" <<'PY'
import json,sys
for line in open(sys.argv[1]):
    item=json.loads(line)
    if item.get('reason')=='compiler-artifact' and item.get('profile',{}).get('test') and item.get('executable'):
        print(item['executable'])
PY
)
codesign --force --sign - --entitlements "$SRC/hvf-entitlements.plist" "$TEST"
DYLD_LIBRARY_PATH="$WORK/lib" "$TEST" virtio::snd | tee "$WORK/audio-tests.log"
cp target/release/libkrun.dylib "$OUT/libkrun.1.dylib.new"
strip -S "$OUT/libkrun.1.dylib.new"
install_name_tool -id @rpath/libkrun.1.dylib "$OUT/libkrun.1.dylib.new"
codesign --force --sign - "$OUT/libkrun.1.dylib.new"
codesign --verify --strict "$OUT/libkrun.1.dylib.new"
mv "$OUT/libkrun.1.dylib.new" "$OUT/libkrun.1.dylib"
cp Cargo.lock "$OUT/libkrun-lite-Cargo.lock"
python3 - "$ROOT" "$WORK" "$OUT" <<'PY'
from pathlib import Path
import hashlib,json,re,sys
root,work,out=map(Path,sys.argv[1:])
library=out/'libkrun.1.dylib'
assert b'/Users/' not in library.read_bytes(), 'Unmapped builder path in release library'
tests=(work/'audio-tests.log').read_text()
match=re.search(r'test result: ok\. (\d+) passed; 0 failed; (\d+) ignored',tests)
assert match and int(match[1])>=32
digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
receipt={'libkrun_commit':'227b2de6ed323fe180e02f871c5f325a90c13cc2',
         'patched_library_sha256':digest(library),
         'patch_sha256':digest(root/'host/libkrun/patches/0030-virtio-snd-pace-capture-startup-and-own-converters.patch'),
         'cargo_lock_sha256':digest(out/'libkrun-lite-Cargo.lock'),
         'features':['gpu','blk','net','input','snd'],'built_in_init_blob':False,
         'audio_regression_tests_passed':int(match[1]),'audio_regression_tests_ignored':int(match[2]),
         'builder_paths_removed':True}
(out/'libkrun-lite-build.json').write_text(json.dumps(receipt,indent=2)+'\n')
print('Built microphone fix:',library)
PY

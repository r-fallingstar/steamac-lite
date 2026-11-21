#!/bin/bash
# Rebuild libwmtr_host.dylib (the DXMT host executor) from this checkout's wmtr/ and the pinned DXMT,
# run the wmtr test suite against it, and write a receipt that stage-wmtr-host.py checks before the
# library replaces the donor's copy. Lite otherwise ships the donor's libwmtr_host, which does not
# have this fork's host changes (e.g. the game frame cap).
#
# Inputs: host/dxmt/build.sh fetch (pinned DXMT + patches), llvm (LLVM 15, ~10 min once) and native
# (airconv; needs the Metal toolchain: xcodebuild -downloadComponent MetalToolchain), plus Homebrew
# meson, ninja, cmake, pkgconf and zstd. Steps whose output is already current are skipped.
# Output: work/build/lite-wmtr/libwmtr_host.dylib and build.json.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
cd "$ROOT"
OUT=$ROOT/work/build/lite-wmtr
DXMT=$ROOT/work/src/dxmt
NATIVE=$ROOT/work/build/dxmt-native
LLVM=$ROOT/work/out/host/llvm15

# build-app.sh pins DEVELOPER_DIR to the Command Line Tools, which have no Metal compiler (airconv's
# shaders and the wmtr test library need it): use the selected Xcode's tools for this step only.
if ! xcrun -sdk macosx -f metal >/dev/null 2>&1; then
    for dir in "$(env -u DEVELOPER_DIR xcode-select -p)" /Applications/Xcode.app/Contents/Developer; do
        if DEVELOPER_DIR=$dir xcrun -sdk macosx -f metal >/dev/null 2>&1; then export DEVELOPER_DIR=$dir; break; fi
    done
fi
xcrun -sdk macosx -f metal >/dev/null 2>&1 || { echo 'No Metal compiler: xcodebuild -downloadComponent MetalToolchain' >&2; exit 1; }

# The fetch step's commit message names the fork commit it reproduces; refetch when the pin changed.
. host/dxmt/pin.env
if ! git -C "$DXMT" log -1 --format=%s 2>/dev/null | grep -q "DXMT ${DXMT_FORK_COMMIT:0:12}"; then
    bash host/dxmt/build.sh fetch
fi
bash host/dxmt/build.sh llvm
[[ -f "$NATIVE/src/airconv/darwin/libairconv.a" && "$NATIVE/build.ninja" -nt "$DXMT/meson.build" ]] || bash host/dxmt/build.sh native
ninja -C "$NATIVE" src/airconv/darwin/libairconv.a libs/DXBCParser/libDXBCParserNative.a >/dev/null

rm -rf "$OUT"
MK=(DXMT="$DXMT" DXMT_BUILD="$NATIVE" LLVM="$LLVM" OUT=build/lite-wmtr)
make -C wmtr "${MK[@]}" host >/dev/null
# `make test` runs ./$(OUT)/...: keep OUT relative to wmtr/ and move the result afterwards.
make -C wmtr "${MK[@]}" test
mkdir -p "$(dirname "$OUT")"
rm -rf "$OUT"
mv wmtr/build/lite-wmtr "$OUT"

python3 scripts/lite/stage-wmtr-host.py --record "$OUT"

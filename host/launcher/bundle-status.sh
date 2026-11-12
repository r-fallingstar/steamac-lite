#!/usr/bin/env bash
# Return 0: bundle now; 2: deliberate binary-only build; 1: required app inputs missing.
should_bundle() {
    local out=$1 f
    local missing=()
    if [[ ${STEAMAC_NO_BUNDLE:-0} == 1 ]]; then
        echo "BUILD RESULT: launcher binary only; no .app was created (STEAMAC_NO_BUNDLE=1)." >&2
        return 2
    fi
    for f in Image initramfs.cpio.gz steamac-layer.img; do
        [[ -f "$out/$f" ]] || missing+=("$f")
    done
    if [[ ${#missing[@]} != 0 ]]; then
        printf 'BUILD RESULT: launcher binary only; no .app was created. Missing: %s\n' "${missing[*]}" >&2
        echo "Next: ./build.sh guest, then host/launcher/build.sh (see docs/upstream/requirements-and-building.md)." >&2
        [[ ${STEAMAC_REQUIRE_BUNDLE:-0} != 1 ]] || return 1
        return 2
    fi
}

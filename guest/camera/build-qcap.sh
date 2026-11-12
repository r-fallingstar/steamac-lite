#!/bin/bash
# Build only qcap.dll from the supported Proton's Wine sources plus the preview fix.
set -euo pipefail
root=$(cd "$(dirname "$0")/../.." && pwd)
work=${CAMERA_BUILD_DIR:-$root/work/camera-release}
mkdir -p "$work"
if pgrep -x steamac-vm >/dev/null; then
    echo 'Stop the SteamOS VM before running the camera build container.' >&2
    exit 1
fi
python3 - "$root" "$work" <<'PY'
from pathlib import Path
import hashlib,json,sys,urllib.request
root,work=map(Path,sys.argv[1:])
p=json.loads((root/'guest/camera/proton-camera.json').read_text())
for url,name,sha in [
 ('https://codeload.github.com/ValveSoftware/wine/tar.gz/'+p['wine_commit'],'wine-source.tar.gz',p['wine_archive_sha256']),
 ('https://github.com/SpookySkeletons/wine/commit/'+p['preview_patch_commit']+'.patch','smarttee-preview.patch',p['preview_patch_sha256'])]:
 path=work/name
 if not path.exists():urllib.request.urlretrieve(url,path)
 with path.open('rb') as stream:assert hashlib.file_digest(stream,'sha256').hexdigest()==sha,name
PY
docker build -t steamac-camera-builder:trixie -f "$root/guest/camera/Dockerfile" "$root/guest/camera"
docker run --rm --network=none -v "$work:/input" -w /input steamac-camera-builder:trixie sh -ec '
    if test ! -d wine-source; then mkdir wine-source; tar -xzf wine-source.tar.gz --strip-components=1 -C wine-source; fi
    if test ! -f wine-source/.steamac-preview-patched; then
        patch -d wine-source -p1 -F0 < smarttee-preview.patch
        touch wine-source/.steamac-preview-patched
    fi
    cd wine-source
    python3 dlls/winevulkan/make_vulkan
    ./tools/make_requests
    ./tools/make_specfiles
    ./tools/make_makefiles
    autoreconf -f
    mkdir -p ../wine-build
    cd ../wine-build
    ../wine-source/configure --enable-archs=x86_64 --with-mingw=gcc --without-x --without-wayland \
        --without-alsa --without-pulse --without-dbus --without-fontconfig --without-freetype \
        --without-gstreamer --without-v4l2 --without-vulkan --disable-tests
    make -j2 dlls/qcap/x86_64-windows/qcap.dll
    x86_64-w64-mingw32-strip --strip-debug dlls/qcap/x86_64-windows/qcap.dll
'
python3 - "$work/wine-build/dlls/qcap/x86_64-windows/qcap.dll" <<'PY'
from pathlib import Path
import hashlib,sys
p=Path(sys.argv[1]);print('Built qcap.dll SHA256:',hashlib.file_digest(p.open('rb'),'sha256').hexdigest())
print('Record the rebuilt payload hash in proton-camera.json before staging a new distribution.')
PY

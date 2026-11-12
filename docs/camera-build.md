# Camera release components

The standard Lite app enables the camera through `SteamacCameraSupport` in its
Info.plist. Existing users receive it through the normal update feed, with the
same bundle ID, preferences domain and SteamOS disk. It is not a separate app.

The release layer contains the frame bridge, the v4l2loopback module and a
source-matched Wine camera module. It contains no experimental runtime observer,
game-log collector, automatic game launcher or original-Proton bind mount.

## Wine module

`guest/camera/proton-camera.json` pins the supported stock Proton files, the Wine
source revision, the Smart Tee preview patch and the distributed module hash.
`guest/camera/build-qcap.sh` downloads and verifies those source inputs, generates
Wine's headers and builds only the x86-64 PE camera module with the Dockerfile in
the same directory. Its Unix backend is the original, matching stock library.
No full Wine replacement or RTSP Proton binary is used in the standard release.

The corresponding source archive contains the original Wine source tarball and
the exact patch. Build prerequisites are Docker and Python 3.11 or newer.
Rebuilt binaries can have a different linker timestamp/hash; record their hash
in the manifest when making a new distribution rather than relabeling them as
the published binary.

## Guest module and frame bridge

The source archive includes Linux 7.2.9, its matching kernel configuration, the
repository's kernel patches, and v4l2loopback revision
`442d720262e150084e7923068fb3c01acc42a253`. `scripts/camera/module-build.sh` prepares
that kernel and builds the external module in the camera builder container.
It expects the kernel archive/configuration in `/input`, the kernel patches in
`/patches`, the v4l2loopback checkout in `/loopback`, and build/output directories
at `/build` and `/out`. The distributed kernel image is unchanged from the pinned
1.9.8-eac.1 donor; the module's kernel configuration hash must match it.

The frame bridge builds in that ARM64 container with:

```sh
gcc -static -O2 -Wall -Wextra -Werror -std=c11 camera-agent.c -o camera-agent
gcc -O2 -Wall -Wextra -Werror -std=c11 camera-colors-test.c -o camera-colors-test
./camera-colors-test
```

`scripts/lite/stage-camera.py` validates the prepared runtime hashes and source
hashes before adding them to the release layer. It records their provenance in
`Contents/Resources/steamac-camera-build.json` and includes the license notices.

## Existing installations and new setup

Before Steam starts, `prepare-proton.py --auto` prepares a private copy-on-write
snapshot of the supported Proton and selects it for VRChat when the existing
selection is the standard automatic setup. The first-run VRChat setup also does
this after Steam finishes downloading the required tools. Both paths run while
Steam and games are stopped. No additional user selection is required.

The installed Steam Proton files are never changed. Unknown Proton revisions,
unfinished downloads and custom compatibility selections are left alone. A
validated private snapshot can keep working independently of a later Steam
Proton update. Copy-on-write is used where supported. On ext4, preparation makes an independent copy after checking available space, with a 4 GiB source-size ceiling.

## Verification

Run the camera and setup fixture tests, native camera/permission/render tests,
and strict localization checks. For the actual guest test, prepare a copy of a
stopped SteamOS disk and set `STEAMAC_CAMERA_TEST_DISK` to that
copy; never use the user's original disk. After building the standard app:

```sh
python3 scripts/camera/prepare-production-test.py
STEAMAC_CAMERA_TEST_DISK=/absolute/path/to/test-clone.img python3 scripts/camera/test-bridge.py --production
```

This boots the standard binary with synthetic frames, prepares the private tool
on Btrfs, checks its selection and receipt, and runs DirectShow tests inside the
actual Steam Linux Runtime and FEX. It checks RGB24, RGB32 preview, a second bound
filter and the expected failure of the unchanged stock control. The VM shuts
down normally. Neither the physical camera nor a game is opened by these tests.

The M1/8 GB face-tracking and automatic-stop checks were reported successful by
the owner on the preceding experimental build. Final release verification must
distinguish these manual checks from the synthetic tests above.

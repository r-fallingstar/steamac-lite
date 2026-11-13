# Private video compatibility build

The app combines the existing FFmpeg 4.4.8 runtime with two Wine PE modules:
`mfmediaengine.dll` and `winegstreamer.dll`. It does not replace Steam's Proton
installation, the WineGStreamer Unix module, or game files.

## Inputs and build

`guest/media/wine-source.json` pins the Valve Wine archive, supported Proton
revision, two local patches, expected patched source files and approved build
image ID. `guest/media/NOTICE` records the Wine license and patch origins.
The corresponding source archive and executed recipe are retained in
`work/media-release/runtime` for the release source package.

Keep the SteamOS VM stopped while Docker is running. With the approved
`steamac-media-builder:trixie` image available:

```sh
bash guest/video/build-codecs.sh
bash guest/media/build-runtime.sh
python3 scripts/lite/record-media-build.py verify
```

The media build uses a fresh source/build directory and runs without container
network access. Vulkan XML inputs come from the pinned Wine archive. It builds
only the two x86_64 PE modules, strips debugging information, and rejects a
payload containing the experimental diagnostic instrumentation. Source, recipe,
compiler/package evidence and output checksums are checked before staging.

The approved compiler image is defined by `guest/media/Dockerfile`, based on a
pinned Debian image. A different image ID requires reviewing and updating
the SDK pin, then rebuilding and validating the runtime. A local receipt is a
stale-input and integrity check; it is not a signed build attestation.

Stop Docker before starting a SteamOS VM. Assemble the app with
`scripts/lite/build-app.sh` and its usual pinned donor/audio/runtime inputs.
`stage-media.py` copies the modules and notices into the packaged guest layer.

## Existing installations

The startup preparation accepts the existing managed Proton receipts and
upgrades them atomically to schema 4. This receipt additionally owns both media
PE modules. It verifies their stock revision before the first replacement and
uses the previous receipt for later upgrades. Unknown changes are left alone.
The existing camera module, private codecs and launcher policy are retained.

No user must select a separate camera/video app or manually replace DLLs.
No runtime diagnostic services or test launch options belong in the package.

## Verification

```sh
python3 scripts/camera/test-prepare-proton.py
python3 scripts/lite/test-media-stage.py
python3 scripts/lite/test-video-build.py
```

These cover ownership, migration, rollback and packaging. They do not establish
VRChat playback. Before release, test the packaged app on a clone of an existing
installation, with normal launch options and diagnostic logging disabled. Check
AVPro and Unity video/audio, normal audio speed, Stop, and playlist switching.
Keep the original SteamOS disk unchanged during that test.

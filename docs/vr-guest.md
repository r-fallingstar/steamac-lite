# VR in the guest: OpenVR runtime and Proton submit path (experimental, M2/M3)

**Status: experimental.** The runtime and wmtr loopback have offline tests. An x86 Linux build of the patched Proton
`vrclient_x64.dll` and Unix library has passed a fake-host test for DXMT texture export and array-slice submits. The
`IVRCompositor_028` bootstrap test still depends on the M6 version adapters. No headset or VRChat game session has been
run; the guest/FEX test and live host connection remain open.

## Source-build sequence

Lite.14 and earlier DMGs are not complete VR builds. The 1.9.8-lite.1 DMG includes the pinned upstream host/Proton VR components and a source-matched guest runtime with the Lite calibration changes. Headset operation is not verified and VR is off by default. The sequence below is for a full source build. Keep an existing app and SteamOS disk separate
from build outputs. You need the [Mac build requirements](upstream/requirements-and-building.md),
including Go and Cargo on PATH, and a separate **x86_64 Linux** build environment with
Podman or Docker. An OrbStack Ubuntu **amd64** machine with x86 translation was reported
working in issue #6; the maintainer has not repeated that full build on that machine.
An arm64 Linux VM is not equivalent. Allow about 4 GB for Proton sources and 14 GB for its build.

1. On the Mac, build host libraries, DXMT and the VR server:

   ```sh
   STEAMAC_NO_BUNDLE=1 ./build.sh host
   ./build.sh dxmt
   ./build.sh vrhost
   ```

2. In the x86_64 Linux checkout, build both guest components. The sniper helper's
   output path is relative to `guest/vr`:

   ```sh
   guest/vr/build-sniper.sh build-sniper
   guest/proton-vrclient/build.sh "$HOME/proton-vrclient" "$PWD/work/out/vr"
   mkdir -p work/out/vr/runtime
   cp -a guest/vr/build-sniper/runtime/. work/out/vr/runtime/
   ```

   If this is a different checkout, copy the resulting `work/out/vr/` tree back to
   the Mac checkout's `work/out/vr/`. It must contain all three files:
   `runtime/bin/linux64/vrclient.so`, `x86_64-windows/vrclient_x64.dll`, and
   `x86_64-unix/vrclient_x64.so`. See [the Proton build notes](../guest/proton-vrclient/README.md)
   for interrupted submodules and rootless Podman prerequisites.

3. On the Mac, build the guest artifacts **after** staging the VR files:

   ```sh
   guest/kernel/build.sh
   scripts/build-image.sh builder rootfs
   guest/mesa/build.sh
   scripts/build-image.sh initramfs layer
   host/launcher/licenses.sh --check-inputs
   STEAMAC_REQUIRE_BUNDLE=1 host/launcher/build.sh
   ```

   The rootfs download is about 4 GB. Guest Mesa requires it; the VR layer requires
   that Mesa output and DXMT's guest payload. Borrowing `Image` and initramfs from
   a DMG, even with their receipts, cannot replace this sequence: the Lite-modified
   layer does not provide a full-source build receipt for your checkout. Never fabricate
   `.inputs.json` files to bypass validation. These commands refresh build artifacts;
   they do not recreate an existing SteamOS disk. For a new disk, also run
   `scripts/build-image.sh disk check`.

Keep all source/build trees and pinned archives until app bundling completes; the
[license inventory](upstream/requirements-and-building.md#license-inputs) needs them.
These steps describe assembly, not proof of hardware compatibility. Test pairing,
tracking and game playback with your actual headset before distributing a VR build.

## How a frame gets out

```
VRChat (x86-64 Windows, under FEX)
  openvr_api.dll → Proton vrclient_x64.dll (PE)             guest/proton-vrclient/patches
      Submit(D3D11 texture): QueryInterface(IMTLD3D11ExportableTexture) → GetMetalTexture
      → Texture_t{ &svr_metal_texture, TextureType_Metal }
  → Proton unix side → <PROTON_VR_RUNTIME>/bin/linux64/vrclient.so   guest/vr (this runtime)
      both eyes → WMTVRSubmitInfo → winemetal unix call 146 (WMTVRSubmit) on the game's own wmtr context
      WaitGetPoses / poses / input / haptics → wmtr_vr_call (WMTR_CTL_VR_QUERY), same context
  → wmtr executor in steamac-vm: exporter (copy into IOSurface swapchain, VRL_SUBMIT) and the cached
    VRL_STATE/TIMING/POSES/INPUT the queries are answered from; haptics → VRL_HAPTICS
  → steamac-vrhost (GPL-3, separate process) → headset
```

* **Textures never leave the wmtr context they were created in.** DXMT's texture handles only mean something in the
  game process's wmtr context, so the runtime finds the already loaded `winemetal.so` (the wmtr client) in its own
  process and calls it directly; it opens no second connection.
* **The executor never waits for VR.** Queries are answered from the newest copy of what `steamac-vrhost` sent;
  `WaitGetPoses` sleeps in the guest until the pacer's wake-up time (converted from the host clock with the offset
  measured on each reply). With no headset connected the queries still return a 90 Hz cadence, so a game does not hang.
* **Poses** are predicted by the host to the frame's display time and extrapolated in the guest (linear and angular
  velocity) for any other time the game asks for (`GetDeviceToAbsoluteTrackingPose`, `GetPoseActionDataRelativeToNow`).
  The per-eye poses sent with a frame are the head pose the game rendered with, offset by half the IPD each.

## Why our own OpenVR runtime and not xrizer on an OpenXR runtime

Both were checked by building them. xrizer (`a1216c7`, GPL-3) builds for x86-64 Linux and its own test suite passes
(84 tests). It cannot take a DXMT texture as it is: its graphics backends accept only Vulkan and OpenGL textures
(`SupportedBackend::new` panics on any other type) and copy the game's texture into runtime-owned OpenXR swapchain
images through that graphics API. A DXMT process has neither. Using it would mean a fork with a new backend, plus a
second runtime underneath (an OpenXR runtime with a custom graphics binding and its own action/binding resolution;
xrizer's `fakexr` test runtime sets action states directly and resolves no bindings), plus an extra copy per eye, and a
GPL-3 component loaded into the game process. Every OpenVR call would cross two API layers under FEX.

The runtime here implements the OpenVR subset directly: about 2.6k lines of C++ (Apache-2.0) plus 1.5k lines of generated stubs for
every interface method. It answers `IVRSystem`, `IVRCompositor`, `IVRInput`, `IVRChaperone`, `IVRSettings`,
`IVRApplications`, `IVRRenderModels`, `IVROverlay`, `IVRScreenshots` and `IVROverlayView` at the versions of OpenVR
2.15.6. Every method the runtime does not implement logs its first call; every interface request is logged
(`STEAMAC_VR_LOG=1`). That gives the record of which versions and methods VRChat really uses.

## Input (M3)

* SteamVR Input: the action manifest, then the game's **own default binding file** for the headset's controller
  family: `oculus_touch` for Quest/Pico/Touch-style controllers, `knuckles` for Index-style ones (falls back to the
  other, then to the first listed).
* Modes: `button`, `trigger` (with `click_activate_threshold`/`click_deactivate_threshold`), `joystick`, `trackpad`,
  `dpad` (click or touch `sub_mode`), `scalar_constant`, `force_sensor`, `grab` (0.7 on / 0.6 off), `toggle_button`.
  Action sets: only the active ones are evaluated; actions report `bChanged`, `fUpdateTime` and the origin hand;
  `ulRestrictToDevice` works per hand.
* Poses: `pose/raw`, `base`, `handgrip` → grip; `pose/tip` → aim. Skeletal actions report finger curls in
  `GetSkeletalSummaryData` (trigger → index, grip → middle/ring/pinky, any thumb touch → thumb). Full bone transforms
  are not produced yet.
* Haptics: `TriggerHapticVibrationAction` and the legacy `TriggerHapticPulse` go to the host as `VRL_HAPTICS`.
* Legacy `GetControllerState` is filled from the same input snapshot.
* Input values arrive as one table per hand (`enum svr_input` in `guest/vr/include/steamac_vr_guest.h`, mirrored by
  `VRL_INPUT_COUNT` in `vrlink.h`): the headset adapter maps its controller inputs to these ids.

## Build and test (no headset, no VM)

On x86-64 Linux:

```sh
make -C guest/vr RUNTIME_LDFLAGS= check     # native toolchain: unit tests + end-to-end
guest/vr/build-sniper.sh                     # release build in the Steam Runtime sniper SDK (podman), then the same tests
```

| test | checks |
|---|---|
| `unit_tests` | JSON reader (escapes, BOM, comments, errors); binding parsing; toggle, grab hysteresis, dpad, trigger thresholds, inactive sets; pose extrapolation forwards and backwards, matrices, projection |
| `run_e2e.sh` | `vr-fakehost` (90 Hz pacing, synthetic head/hand motion, frame-keyed input script `tests/data/script.txt`) + `vr-testapp`, which loads `vrclient.so` the way Proton does and runs 150 frames: interfaces and versions, render size, projection, eye transforms, device classes, activation events, properties, frame pacing (no skipped frames), head yaw consistent with the motion model, 100 ms prediction, actions pressed/released in the scripted windows, `bChanged` exactly twice, per-hand restriction, pose actions (grip and aim), skeleton summary, legacy controller state, both eyes submitted per frame. The fake host checks every submit against the frame it issued (frame id, display time, eye poses centred on that frame's head pose and one IPD apart) and that the haptic event reached the right hand only. Run for both controller families. |
| `wmtr/tests/wmtr_loopback` (macOS) | the executor side: `WMTR_CTL_VR_QUERY` through the ring before any host state (local cadence), after `VRL_STATE`/`VRL_TIMING`/`VRL_POSES`/`VRL_INPUT`, the cadence after the pacer's frame, haptics → `VRL_HAPTICS`, an unknown request refused |

The same `vr-fakehost`/`vr-testapp` pair runs in the VM guest under FEX (`STEAMAC_VR_SOCKET` selects the socket
transport instead of wmtr).

## Proton client build and test (x86-64 Linux)

`guest/proton-vrclient/build.sh [WORK] [OUT]` checks out the Proton commit in `pin.env`, applies the local patch set,
builds Proton's `vrclient` target in its pinned Steam Runtime SDK, and writes both PE and Unix artifacts to the guest
layer layout. It reuses the named WORK tree and refuses to replace modified Proton source. The first build requires
about 4 GB of source and 14 GB for the build tree; do not start it unless the x86 build host has adequate free space.

`guest/proton-vrclient/tests/run.sh WORK <guest/vr build>` exercises the patched PE client under the matching Wine
build with fake DXMT COM textures and `vr-fakehost`. On a machine without the Proton runtime's `_028` interface, use
`COMPOSITOR=IVRCompositor_029 MANUAL_REGISTRY=1` only for isolating texture conversion; that bypasses Proton's own
registry bootstrap and does not count as the full integration gate. The full VRChat-compatible path must exercise the
normal `_028` registry initialization, export both `HmdSystemFactory` and `VRClientCoreFactory`, then pass under FEX.

## Deploying

1. Set `PROTON_VR_RUNTIME=<dir>` where `<dir>/bin/linux64/vrclient.so` is the sniper build.
2. Install the rebuilt `vrclient_x64.dll` and `vrclient_x64.so` into the active Proton compat tool.
3. Use DXMT with `IMTLD3D11ExportableTexture` (DXMT `vr-export`) and a wmtr client exposing `wmtr_vr_call`.
4. Enable the steam-vr-path guest-layer hook; verify disable/restore returns the stock Proton files.

The installer hook is present, but it has not yet been verified end-to-end under FEX or against the live launcher/host.

## Licences

`guest/vr` is Apache-2.0, except `third_party/openvr/openvr.h` (Valve, BSD-3-Clause). `guest/proton-vrclient/patches`
are LGPL-2.1-or-later like the Proton/Wine code they change. Nothing here contains xrizer, WiVRn or Monado code.

## Controller pose calibration (issue #2, awaiting hardware verification)

The runtime currently uses OpenXR grip poses for OpenVR controller devices. The
reported difference from SteamVR's raw origin still needs a profile-specific fix.
`SVR_PROFILE_TOUCH` also covers Pico-like controllers, so a Touch-specific transform
cannot safely be applied to every device with that profile. No guessed default
transform is installed by this change.

For source-build testing, the guest runtime accepts these **game process** variables:

- `STEAMAC_VR_GRIP_OFFSET=x,y,z[,pitch,yaw,roll]`
- `STEAMAC_VR_AIM_OFFSET=x,y,z[,pitch,yaw,roll]`

Values describe the right controller's local coordinates in metres and degrees.
Rotation is `qx * qy * qz`, post-multiplied onto the tracked orientation. The left
hand mirrors translation X and rotation yaw/roll. Position and linear velocity are
both transformed, including `omega cross (R*t)`. Angles must be within ±360° and
positions within ±10 m; malformed/non-finite values disable both offsets and log
an error. Unset values leave tracking unchanged. Head poses are never changed.

The calibration applies once to grip/aim pose reads, including frame poses,
predicted game poses and pose/skeleton actions. It deliberately calibrates all
uses of those tracked origins; it is not yet a distinction between OpenVR raw and
grip action spaces. Rebuild the runtime and guest layer before testing it.

For a neutral diagnostic launch, add `STEAMAC_VR_LOG=1
STEAMAC_VR_GRIP_OFFSET=0,0,0` before the existing `%command%` in Steam launch options,
keeping all existing EAC/VR options. Set a measured offset for calibration; remove
these variables to return to the original behavior. Values are read when the game
initializes its runtime, so close and reopen the game after changing them.

The native unit suite checks mirroring, local rotations, predicted positions,
velocity, invalid inputs and unchanged head/default poses. Live Quest tracking and
cross-interface agreement under FEX still require a hardware test. Please provide
the observed per-hand displacement with controllers held level, controller model,
current bindings and any measured offsets before treating issue #2 as resolved.

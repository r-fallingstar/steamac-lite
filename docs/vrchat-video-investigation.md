# VRChat video investigation (issue #1)

Status: open; reported by multiple users. The H.264 initialization failure and
N-times-speed audio are separate problems. Neither has been reproduced by the
maintainer in the reported M3 Pro / FEX / custom VR build. Do not treat the reporter's Steam-client licensing
hypothesis as an established cause. An unsuccessful `avcodec_open2` does not by itself
identify why the decoder failed.

The Lite layer does not replace Steam's `libavcodec` or contain AVPro's AudioSource
buffer manager. The report's read counts suggest that audio is being consumed more
than once, but they do not establish whether AVPro, Wine's source reader or timing
under FEX causes that behavior. The OpenVR pose runtime has no AudioSource count
with which to correct it. Globally dividing playback speed by a speaker count would
not resolve that ownership problem.

AVPro's documentation describes audio extraction through `OnAudioFilterRead()` and
an `AudioOutputManager` for multiple outputs. This gives a place to investigate; it
is not evidence that the VRChat version has the same implementation:
[AudioOutput](https://www.renderheads.com/content/docs/AVProVideo/articles/component-audio-output.html),
[AudioOutputManager](https://www.renderheads.com/content/docs/_AVProVideo-v3/api/RenderHeads.Media.AVProVideo.AudioOutputManager.html).

## Read-only decoder probe

`guest/diagnostics/avcodec-probe.c` loads an explicitly selected library and prints its
actual path/version, the resolved `avutil` path/version when available, codec build
configuration, CPU count/feature flags, probe architecture, and the numeric
`avcodec_open2` result and error text for `h264` and `valve_h264`. It does not replace libraries or load a
video. A successful empty-context initialization is not a playback test.

Build it on **x86_64 Linux** in the sniper SDK environment used for the failing game:

```sh
cc -O2 -Wall -Wextra -o avcodec-probe guest/diagnostics/avcodec-probe.c -ldl
```

Then run the x86_64 binary **under FEX in the same Steam Runtime environment and with
the same library search paths as the failing game**, passing the actual loaded
`libavcodec.so.58` from the report. Running it in a native Linux build VM tests that
VM, not the FEX failure. Do not change global `LD_LIBRARY_PATH` or copy libraries
into Steam to make this probe run. If its dependencies cannot be resolved, include
the `dlopen` error instead of replacing them.

```sh
./avcodec-probe /absolute/path/to/Steam/ubuntu12_64/libavcodec.so.58
```

## Bounded follow-up (2026-11-12)

The saved issue localizes the video failure to decoder initialization after URL
resolution, HTTP headers and H.264/AAC MP4 demuxing succeed. The broken
`steamrt64/video` symlinks alone do not explain a failure in a library that the
process actually loaded from `ubuntu12_64`. The reporter's successful replacement
changed four libraries at once, so it implicates that library set/configuration
but does not isolate a codec defect, dependency mismatch, FEX instruction path,
thread setup or Steam integration. None of these deeper causes is confirmed.

`work/release-lite14/avcodec-probe.log` is the output of the disposable-library
regression test, **not** a run against Steam's decoder. It cannot establish that
H.264 works on the guest. The repository's `guest/proton-vrclient/pin.env` identifies
our vrclient build, not the reporter's installed Proton Experimental build.

The inspected Lite build and `guest/layer/usr/lib/steamac/vrchat-setup` install FEX
and configure EAC/Proton launch options; they do not install a codec or set
GStreamer decoder options. `audio-layout` configures physical VirtIO channels and
scheduling, not world AudioSource consumers. `guest/vr/runtime` supplies OpenVR
poses, rendering and frame timing, not Media Foundation source-reader buffers.
There is no evidence supporting a production codec swap, a global CPU/thread
setting, a playback-rate change or a pose-runtime audio fix here.

### Decoder experiment

Use the same x86_64 Linux probe and runtime environment as above. Run separate
processes with the **same original library path**, preserving stdout and stderr:

```sh
./avcodec-probe --verbose /absolute/path/to/Steam/ubuntu12_64/libavcodec.so.58 > codec-default.log 2>&1
./avcodec-probe --verbose --threads=2 /absolute/path/to/Steam/ubuntu12_64/libavcodec.so.58 > codec-threads2.log 2>&1
./avcodec-probe --verbose --threads=1 /absolute/path/to/Steam/ubuntu12_64/libavcodec.so.58 > codec-threads1.log 2>&1
./avcodec-probe --verbose --threads=2 --cpu-flags=0 /absolute/path/to/Steam/ubuntu12_64/libavcodec.so.58 > codec-threads2-cpu0.log 2>&1
```

The controls affect only the probe process. `--threads=N` accepts 0–16 (0 asks
FFmpeg to choose); an unavailable/rejected control fails explicitly rather than
silently testing defaults. `--cpu-flags=0` disables FFmpeg's runtime CPU feature
dispatch; it does not change FEX's advertised CPU or remove compiled instructions.
`--verbose` requests FFmpeg debug logging; a silent failure can still be silent.
Optional provenance exports may be unavailable in custom builds.

These controls use the public FFmpeg 4.3 APIs:
[CPU flags](https://github.com/FFmpeg/FFmpeg/blob/n4.3.6/libavutil/cpu.h),
[AVOptions](https://github.com/FFmpeg/FFmpeg/blob/n4.3.6/libavutil/opt.h),
[thread defaults](https://github.com/FFmpeg/FFmpeg/blob/n4.3.6/libavcodec/options_table.h),
[logging](https://github.com/FFmpeg/FFmpeg/blob/n4.3.6/libavutil/log.h).
The empty-context FFmpeg default is one thread; the default probe is therefore
not a multithreaded reproduction. For comparison, upstream
[gst-libav 1.18.6](https://github.com/GStreamer/gst-libav/blob/1.18.6/ext/libav/gstavviddec.c)
sets thread counts before opening the codec and reports the generic failure when
that open fails. This explains the experiment, not the installed plugin's version.

Interpretation and next steps:

- If one thread succeeds and two fail, investigate thread initialization under
  FEX with the exact installed plugin. If only disabling CPU flags changes the
  two-thread result, investigate runtime CPU dispatch. Neither result alone
  justifies a game-wide setting; verify actual decoding first.
- If all fail, keep the numeric error, configuration and dependency provenance.
  This still does not establish a licensing/Steam-client cause. Compare with an
  already-backed-up working library set in a separate process only if available;
  do not mix new libraries into Steam or change its global search paths.
- If all succeed but VRChat fails, the empty-context test did not reproduce the
  failure. Next decode the same local public H.264 MP4 through the installed
  **x86_64** GStreamer stack under FEX, comparing `avdec_h264` defaults with
  `avdec_h264 max-threads=1`, using `fakesink` to isolate decoding from rendering
  and audio. Keep caps/plugin versions and confirm loaded library paths; success
  in a different native GStreamer installation does not test the game stack.

### Audio experiment

The reported audio sample duration and format are internally consistent:
1024 / 44100 = 0.02321995 seconds; stereo float32 is 352800 bytes/second.
At 25 fps, equal-duration steady-state consumption predicts about 1.723 audio
samples per video sample. The reported 3.38 is approximately twice that, but
request counts alone cannot distinguish duplicated consumption from prefetch,
retries or multiple readers. This is a separate observation from H.264 failure.

In one public test world, use the same media and settings with one and then two
AudioSources. After startup buffering, capture matched 5–10 second windows with
source-reader identity, thread, request/completion times, HRESULT/stream flags,
sample timestamp, duration and sample count. Count **completed sample durations
per reader**, excluding empty/retried calls, and compare with monotonic elapsed
time and video progress. If audio advances about 2 seconds per real second only
with two outputs, distinguish sequential extra samples (buffer consumed twice)
from repeated timestamps (duplicated delivery). Record the VRChat/AVPro build and
whether the symptom occurs in desktop and VR modes. Only then choose an AVPro,
Wine source-reader or timing investigation; no buffer owner is established yet.

### Local validation

Run `DEVELOPER_DIR=/Library/Developer/CommandLineTools python3 scripts/test/avcodec-probe.py`.
This compiles with warnings as errors and uses temporary codec/utility libraries
to check dependency provenance, numeric failures, requested CPU/thread/log
controls, process isolation, rejected options and missing exports. It does not
exercise real FFmpeg, Linux/FEX, media playback or the game's audio path.
No VM, Docker, installed app or production disk is needed for this check.

## Evidence needed next

The clone-only `guest/diagnostics/video-test-runner --collect` records the FEX
launch manifests, both Runtime 4 layouts, ELF interpreter architectures, and Steam
codec hashes without starting a program. Its optional `--run` mode refuses a
rootfs that cannot resolve the probe's exact x86_64 interpreter. That validation
does not construct pressure-vessel's filesystem namespace or prove equivalence
to the game's runtime. The initial Media Foundation camera diagnostic failed
before Proton started, so it says nothing about camera compatibility.

A [September 2026 Proton report](https://github.com/ValveSoftware/Proton/issues/1199#issuecomment-5699247563)
describes normal video with 2× audio in Pocket Storm and improvement using
GE-Proton 11-6, with seeking still broken. This is a useful whole-build comparison;
it does not establish the same AudioSource-count bug. The
[GE-Proton 11-6 release](https://github.com/GloriousEggroll/proton-ge-custom/releases/tag/GE-Proton11-6)
includes AVPro/Media Engine work, but the local report uses an asynchronous source
reader without a media session. Do not attribute the improvement to an individual
patch or replace the configured Proton automatically. Compare builds only in the
test clone after preserving the required EAC integration and existing prefix.

- Proton's exact build identifier, FEX version, and SteamOS build. “Experimental”
  alone changes over time and cannot identify the tested binary.
- The first decoder failure, its preceding caps messages, and which library the
  game actually loaded. Compare the original Steam libraries with the reporter's
  already-backed-up workaround in separate logs; no new library swap is requested.
- For the same media and settings, a 5–10 second log excerpt with one AudioSource
  and two: source-reader identity, thread, ReadSample request/completion times,
  sample timestamp/duration and number of samples. Comparing only total call
  counts can mix multiple readers, retries or startup buffering.
- A reproducible public world/video or minimal repro, if available. No private
  world assets or full game files are needed.

Review logs before sharing: omit account identifiers, local personal paths,
private-world links, expiring media URLs and authentication data. Keep the issue
open until an actual playback test verifies the fix.

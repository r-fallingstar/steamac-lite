# VRChat video investigation (issue #1)

Status: open for reporter confirmation. The maintainer confirmed AVPro and Unity
playback in Tokyo Sky Home on an M1 / 8 GB test clone after the private decoder
priority fix. The separate N-times-speed audio report has not been reproduced in
an actual multiple-AudioSource player; no dedicated audio-speed patch is claimed.
Do not treat the reporter's Steam-client licensing
hypothesis as an established cause. An unsuccessful `avcodec_open2` does not by itself
identify why the decoder failed.

The candidate supplies private FFmpeg libraries without replacing Steam's
`libavcodec` and does not contain AVPro's AudioSource
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
At that stage, no actual FEX decoder comparison supported a production codec
change. The later comparison below provides that missing evidence for the private
codec candidate. A global CPU/thread setting, playback-rate change or pose-runtime
audio fix is still unsupported.

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

## Actual FEX decoder comparison (2026-11-12)

The test used an independent copy of the stopped normal SteamOS disk on the
maintainer's M1 / 8 GB Mac, with macOS 27.2, FEX `eac-2610.5`, Proton
`experimental-11.0-20261105c-x86_64` (Wine `e8ca5806`), and Steam Runtime
`4.0.20261021.265997`. The original disk and normal preferences were retained.
No game, physical camera, or microphone was opened during these decoder tests.

The x86 probe ran inside the actual Steam Runtime / FEX filesystem view.
Steam's `ubuntu12_64/libavcodec.so.58` SHA-256 was
`2f8494ad8dff5846b082441b83ae16bcd2e100eea17d5fcc18fbf13eebd6b3a0`.
The loaded versions were avcodec 58.91.100 and avutil 56.51.100. Both `h264` and
`valve_h264` returned **-1 (Operation not permitted)** from `avcodec_open2`.
One thread, two threads, and two threads with runtime CPU flags disabled all
failed identically. This establishes the failure in this library/environment;
it does not establish the internal reason for the denial.

A source-built FFmpeg 4.3.6 control opened H.264 and decoded the public Wine test
MP4 through the same Proton Source Reader, synchronously and asynchronously.
The maintained ABI-compatible [FFmpeg 4.4.8 release](https://ffmpeg.org/download.html)
was then built in the pinned x86 Steam Runtime SDK. The four libraries keep the
same major SONAMEs: avcodec 58, avformat 58, avfilter 7, avutil 56. Its source pin,
configuration and build steps are in `guest/video/ffmpeg-source.json` and
`guest/video/build-codecs.sh`.

The candidate installs them into the existing **private** compatibility tool,
not Steam's installed libraries or original Proton. The actual guest test
upgraded a schema-1 camera snapshot to schema 2, kept the camera module and
Steam tool identity, validated the new manifest, and checked that original
Steam decoder and Proton camera hashes stayed unchanged. The migration has
104 fixture checks, including the 38 existing camera checks, rollback/recovery,
unknown stock updates, custom selections and file isolation. The follow-up fault
injections cover a changed/disappeared published target and interrupted backup
cleanup. Cleanup revalidates the successor and retains a directory-identity-bound
transaction marker until backup deletion completes, allowing a later stopped
startup to resume without treating arbitrary replacement directories as owned.

### Playback evidence and limits

`guest/diagnostics/mf-video-probe.c` is a standalone Source Reader client. It
logs types, HRESULTs, valid buffer lengths versus capacity, payload hashes,
sample timestamps/durations and completed totals. It has independent process,
read-count and time bounds. It neither renders video nor drives an audio device.
`--timeline-order` requests the stream whose delivered timeline is behind;
`--pace-audio` schedules audio-only reads by valid PCM frames and sample rate.
Neither changes the Source Reader or the game's playback speed.

The canonical fixture is eight seconds of public Wine test imagery rendered to
a continuous H.264 stream, with synthetic stereo tones encoded as AAC. Native
AVFoundation verification produced 200 decoded frames at 25 fps and 352800
44.1-kHz audio frames (eight seconds). A passthrough concatenation with edit lists
was rejected as a timing reference after it produced repeated timestamps under
GStreamer; successful API exit alone is insufficient validation.

With the private 4.4.8 runtime, local sync and async reads reached EOS with all
200 video frames, exactly eight seconds of video duration, and no backward video
timestamps. AAC returned about 8.057 seconds of valid PCM; one startup timestamp
regression/priming discrepancy remains visible. An eight-second PCM WAV control
returned about 7.999 seconds of PCM in about 8.3 seconds with audio pacing enabled.
These tests do **not** reproduce the reported N-times-speed AudioSource behavior.

A range-capable loopback HTTP fixture allows successful opening and decoded
samples, including the complete short Wine MP4. The eight-second HTTP case still
returns only **150/200 video frames**, even with video-only or timeline-ordered
reads. It must not be recorded as a full playback pass or used to close the issue.
The next check is actual YamaPlayer playback in the user-supplied
[Tokyo Sky Home](https://vrchat.com/home/world/wrld_09f7ceb5-2d4f-4dc4-a2cf-2a32a7af35df/info),
for both AVPro and Unity backends and multiple speaker outputs.

The owner then tested the first candidate in Tokyo Sky Home with YamaPlayer.
Both AVPro and Unity remained black. Inspection of that test clone confirmed
the schema-2 receipt, the four candidate codec hashes, and the `steamac_camera`
selection. The game log showed successful YouTube URL resolution, but did not
establish which decoder library was mapped at playback time. This is an actual
failed game test; the standalone decoder success must not be described as a
fix for the world's playback. A subsequent clone-only diagnostic records mapped
library file paths/hashes, without attaching to or reading game process memory.

A first attempt to run the standalone probe through Proton's full `run` verb
timed out before the probe banner. It had reached `steam.exe` in a headless boot;
the exact blocking function is unknown. Its wrapper initially discarded status
124 and reported VM exit zero, so that run is explicitly a failed harness test.
Further comparisons separate prefix setup, the `runinprefix` verb, architecture
choice and GStreamer registry forking rather than infer a codec regression.

The second GUI test recorded the actual game's library metadata. Although its
GStreamer plugin came from the private compatibility tool, the game mapped all
four FFmpeg libraries from Steam's `ubuntu12_64` directory. The mapped avcodec
SHA-256 was **2f8494ad8dff5846b082441b83ae16bcd2e100eea17d5fcc18fbf13eebd6b3a0**,
identical to the library that returned EPERM in the standalone reproduction.
Its inherited search path put Steam's three video directories ahead of the
private tool directories. This establishes that the actual game did not use
the candidate codecs; the earlier explicit-path diagnostic had masked that
launch-path difference. A pinned private-launcher priority policy now prepends
the private codec directory immediately after Proton adds Steam's video paths.
Its exact source anchor uses `steam_linux_path`; the original launcher SHA-256 is
`6d0cd1d4196d73a970ed4ce2e569f3a2003beae3beb0c7951fa08c22cd2772a1`.
The schema-3 upgrade succeeded on the isolated test clone and verified that
Steam's original files remained unchanged. The patched private launcher hash is
`1f1e18d4045a4e247ab73cb7f923de7ce219d0c76a60974cb3b388d0e744f33f`.
The phased headless Proton harness then exited 255 before container entry, so it
is not a playback pass.

The third GUI run then recorded all four actual game mappings in the private
tool, matching the verified build: avcodec `e82ac2ca…`, avutil `59c790c3…`,
avformat `20db0db1…`, and avfilter `0f4badeb…`. On November 13, 2026 (JST), the
maintainer tested the requested AVPro → Unity sequence in Tokyo Sky Home and
reported “動きました！すべて大丈夫そうです！” in response to the video, audio and
playback-speed check. This is an owner-confirmed game playback pass on that
machine/world, not a claim that every stream or the original reporter's separate
multiple-AudioSource speed issue is resolved. Keep issue #1 open pending the
reporter's retest.

The packaged synthetic camera regression also passed all five cases after this
change (stock RGB32 negative control, private RGB24 capture, RGB24/RGB32 preview,
and a second bound filter). The test did not open a physical camera or request
camera permission and verified that the original Proton camera module was
unchanged.

The initial native-probe launcher incorrectly replaced the runtime's library
search path and prevented the ARM FEX loader from finding libstdc++. Prepending
the selected x86 codec path while preserving the runtime-provided paths fixed
the diagnostic launch. This was a harness error, not the H.264 root cause.

No game-wide CPU flags, speaker-count rate division, arbitrary timestamp sleeps,
or untested GE patch set is enabled by the candidate. Audio-source lifetime,
seek ordering, callback ordering and buffer capacity are research candidates;
none is a demonstrated fix for the reported audio problem yet.

### Reusing the standalone decoder probe

Build with the cached MinGW-w64 x86 compiler, only while the SteamOS VM is
stopped. Run inside the same Steam Runtime/FEX environment as the comparison
above, with an independent diagnostic Wine prefix:

```sh
x86_64-w64-mingw32-gcc -std=c11 -O2 -Wall -Wextra -Werror -municode \
  guest/diagnostics/mf-video-probe.c -o mf-video-probe.exe \
  -lmfreadwrite -lmfplat -lmfuuid -lole32 -lpropsys -luuid
wine mf-video-probe.exe --async --timeline-order --expect-video-frames=200 \
  --max-samples=1200 --max-ms=20000 'Z:\\tmp\\canonical-8s.mp4'
```

`--expect-video-frames` makes premature EOS or a sample/time limit fail the
known-frame-count fixture rather than accept a partially decoded video. It
counts nonempty video samples, so use fixtures with one decoded frame per sample.
The ordinary exit-zero result only establishes nonempty data for each requested
stream and successful teardown. Check actual frame counts, EOS, durations and
timestamps before describing a file as completely decoded.

Only local Windows paths and public or loopback HTTP(S) URLs are accepted.
Preserve the Steam Runtime's library search paths when prepending private codec
paths. Drain both output streams and enforce an external process timeout in
addition to the probe's own deadline. No game process inspection, camera access
or audio-device access is involved.

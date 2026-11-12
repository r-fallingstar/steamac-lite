# VRChat video investigation (issue #1)

Status: open. The reported H.264 initialization failure and N-times-speed audio are
separate problems. Neither has been reproduced by the maintainer in the reported
M3 Pro / FEX / custom VR build. Do not treat the reporter's Steam-client licensing
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
actual path/version, the probe architecture, and the numeric `avcodec_open2` result
and error text for `h264` and `valve_h264`. It does not replace libraries or load a
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

## Evidence needed next

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

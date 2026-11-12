# Building the Proton VR client

Run `build.sh` on **x86_64 Linux**, with Bash, Git, GNU Make, Python 3 and Podman or Docker.
This does not run directly on macOS or on an arm64 Linux VM. On an Apple Silicon Mac,
an OrbStack Ubuntu amd64 machine with x86 translation is one option reported in issue #6;
the full build on that machine has not been repeated by the maintainer.

```sh
guest/proton-vrclient/build.sh "$HOME/proton-vrclient" /path/to/steamac-lite/work/out/vr
```

The first argument is a disposable source/build cache, not your main checkout. The first
build downloads about 4 GB of sources and needs about 14 GB for its build tree. Existing
local source edits are not force-reset. An interrupted, empty submodule checkout is
restored; a populated checkout with missing files stops with a diagnostic for inspection.

## Rootless Podman

The Linux user needs subordinate UID/GID ranges in `/etc/subuid` and `/etc/subgid`, and
the `newuidmap` / `newgidmap` helpers. Ask the machine administrator to configure those
if they are absent. `podman unshare id` can check that the user namespace is available.
Do not run the build as root to work around missing mappings.

If Podman warns that there is no systemd user session, configure its cgroup/event backend
for that Linux environment. Podman's `cgroupfs` manager and `file` event backend may be
suitable on a VM without a systemd user session. This script does not rewrite
`~/.config/containers/containers.conf`, migrate containers or change UID/GID ranges.

The local `configure.sh` patch keeps diagnostic output on stderr, separate from the UID
returned on stdout. Warnings remain visible. A failed container probe or a non-numeric
UID stops configuration rather than silently continuing with an invalid permission map.

See [Podman options](https://docs.podman.io/en/latest/markdown/podman.1.html) and
[rootless namespace checks](https://docs.podman.io/en/latest/markdown/podman-unshare.1.html).

## Outputs and tests

The output directory receives `x86_64-windows/vrclient_x64.dll` and
`x86_64-unix/vrclient_x64.so`. It is separate from `guest/vr`'s OpenVR runtime.
Build that runtime with `guest/vr/build-sniper.sh` and stage it under
`work/out/vr/runtime/` before assembling a layer; see [the VR source-build steps](../../docs/vr-guest.md).

`tests/run.sh WORK <guest/vr build>` exercises the built PE client under its matching Wine.
`python3 scripts/test/proton-source.py` checks source checkout/recovery with disposable
local repositories. `python3 scripts/test/proton-configure.py` checks the UID probe against
the pinned upstream configure script without starting a container.

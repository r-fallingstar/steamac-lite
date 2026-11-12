# steamac Lite — adaptive Mac profiles

**English** · [日本語のREADME](README.ja.md)

**Illustrated setup guide:** [日本語](https://r-fallingstar.github.io/steamac-lite/?lang=ja) · [English](https://r-fallingstar.github.io/steamac-lite/en/) · [한국어](https://r-fallingstar.github.io/steamac-lite/ko/) · [简体中文](https://r-fallingstar.github.io/steamac-lite/zh-CN/)

[Update support](https://r-fallingstar.github.io/steamac-lite/en/support/) covers in-app and DMG updates, microphone access, and troubleshooting.

**[Download the Mac app (.dmg, Apple Silicon)](https://github.com/r-fallingstar/steamac-lite/releases/download/v1.9.4-lite.14/SteamAC-Lite-1.9.4-lite.14-macos-arm64.dmg)** · [Release notes](https://github.com/r-fallingstar/steamac-lite/releases/tag/v1.9.4-lite.14) · [はじめての導入手順](docs/quick-start.ja.md)

Lite.13 checks microphone access before starting SteamOS. When needed, it offers the macOS permission prompt or a link to Microphone settings. Access status is also available in Settings → Sound. Ad-hoc builds may need permission again after an update.

Lite.9 adds in-app update notifications and verified downloads from this fork’s GitHub releases. Choose **Update**, then **Install and Relaunch**. The SteamOS disk and settings are kept. Lite.8 and older need one manual upgrade to Lite.9 or later first. [Update behavior and publishing](docs/in-app-updates.md).

Lite.6 fixes silent microphone input in SteamOS. [Cause, fix and validation](docs/microphone-fix.md).

Open **SteamAC Lite.app** inside the DMG and choose **Install and Open**. The app copies itself into Applications and opens the installed copy. No build tools are needed. This is an experimental, ad-hoc signed and unnotarized build; SteamOS and games are downloaded separately. The optional **VRChat setup** bundles the patched FEX and prepares Proton/EAC and launch options after Steam sign-in. Steam download confirmations remain user actions; no game is started. See [the setup flow](docs/vrchat-setup.ja.md).

This fork chooses VM RAM, vCPUs and initial resolution for the Mac, keeps a 3 GiB VM / 4 GiB guest disk-swap profile on 8 GB Macs, defaults to 60 Hz, detects physical US/JIS keyboards, and enables Japanese input through SteamOS's existing IBus/Anthy. Manual settings take priority. Game frame rates and compatibility are not guaranteed. See [automatic profiles](docs/performance-profiles.md), [8 GB limitations](docs/8gb-profile.md), and [keyboard / Japanese input](docs/japanese-input.md).

The app supports English, Japanese, Korean, Simplified Chinese and Russian. Initial setup detects the Mac’s current input source independently of the app language and physical US/JIS geometry. ABC/US starts with direct Latin input; supported Japanese, Chinese Pinyin and Korean 2-set sources use the corresponding method. All three input engines remain available without extra downloads. See [input methods and shortcuts](docs/cjk-input.md).

On a new SteamOS disk, Steam starts in the language selected in the launcher. Existing Steam language settings are preserved. A fresh-disk test completed all FEX/Proton/EAC downloads and VRChat setup with manual Steam confirmations. See [validation and limitations](docs/validation-lite.5.md).

## 日本語

Apple Silicon向けの実験版です。8 GBではVMのRAMを3 GiBに抑え、ゲスト用ディスクスワップ4 GiB、初期描画960×600を使います。16・18 GBでは1440×900、24 GBでは1600×1000、32 GB以上では1920×1200を目安に、画面に収まる大きさへ調整します。既定は60 Hz、DXMT優先です。自分で選んだ設定は保持します。60 Hzは表示更新頻度であり、ゲームの60 fps動作を保証するものではありません。

Mac側の物理キーボード情報からUS/JISを起動時に判別し、Steamとゲームの配列へ反映します。日本語入力は既存のIBus・Anthyを使います。最初は英数入力です。必要に応じて**Control＋.**でAnthyを選び、**Control＋Space**で日本語入力へ切り替え、Spaceで変換、Enterで確定します。JISの「かな」「英数」キーにも対応します。

詳細は[日本語README](README.ja.md)、[導入・ビルドと制限](docs/8gb-profile.md)、[日本語入力と配列](docs/japanese-input.md)を参照してください。作者のM1・RAM 8 GBのMacでVRChatの動作を確認しました。FPS、重いワールド、長時間の安定性は測定していません。

---

The original upstream documentation follows. Its 16 GB minimum and performance figures describe the upstream build, not validation of this experimental 8 GB profile.

# steamac with genuine-EAC games and a DXMT graphics path

**English** · [Русский](README.ru.md) · [简体中文](README.zh.md)

**A fork of [steamac](https://github.com/fxgl/steamac) for Apple silicon Macs. It runs x86-64 Windows games with genuine
Easy Anti-Cheat (verified in game: VRChat; Mini Royale also passes EAC), with a choice of two graphics paths.**

- **Vulkan (classic)**: Direct3D through DXVK on Vulkan inside SteamOS (Venus), then KosmicKrisp or MoltenVK on the Mac.
  This is upstream steamac's path.
- **DXMT (lean)**: Direct3D 11 through [DXMT](https://github.com/3Shain/dxmt). Its Metal calls run natively on the Mac
  over a dedicated virtio-gpu channel, so there are fewer translation layers.

**Like it? Help it along.** A star on the repository, an issue when something breaks (with your Mac model and the
log), and pull requests are all welcome. If you keep a fork with a fix or an improvement, please open a pull request
here too: it gets reviewed, credited to you and shipped to everyone in the next release.

**Found a bug?** Please report it here (an issue, or a pull request with a test) instead of fixing it only in your own
fork, so everyone gets the fix. This fork sends nothing to libkrun, Mesa, FEX or Proton itself; steamac changes are
discussed with its maintainer directly. If you have reviewed a change here and think it is good enough for one of those
projects, you are welcome to submit it there yourself: keep its test with it, follow that project's process, and mention
where it came from. FEX code changes go to [StonkGuy/FEX](https://github.com/StonkGuy/FEX) as a pull request against the
current `eac-<release>` branch, with a test in its `eac-tests/`.

The EAC client is the stock one from the Proton EasyAntiCheat Runtime. Nothing fakes, replays or short-circuits its
result. Not affiliated with FX GAMES, Valve, Epic Games, VRChat or the DXMT authors.

Status: verified on one Mac (M2, 16 GB). VRChat passes EAC and enters a world on both graphics paths. The default is
the Vulkan path; DXMT is a setting you turn on. Measured on that Mac: VRChat about 29-44 fps on Vulkan and 76-78 fps on
DXMT (single runs, see [docs/eac-performance.md](docs/eac-performance.md)).

## Requirements

| you need | notes |
|---|---|
| an Apple silicon Mac | verified on an M2 MacBook Air, 16 GB, macOS 27.0; other Macs are untested |
| macOS 15 or newer | KosmicKrisp (the faster Vulkan driver) needs macOS 26. The DXMT path's host library is built for macOS 15.5 or newer |
| free disk space | we recommend about 20 GB free on the Mac for the SteamOS disk and its download cache, plus room for the games themselves (our estimate; it may vary). Measured: about 14 GB on the disk's volume while the disk is created, about 9 GB afterwards. The home size is chosen at creation and can be enlarged later with Grow Disk |
| memory | 16 GB minimum; less is not supported. Automatic VM RAM is half of the Mac's RAM (4-16 GiB) |
| a Steam account | games are installed and run inside SteamOS |

## Install and first launch

1. Build the app from this fork's `main` branch or a [release](https://github.com/StonkGuy/steamac/releases) tag:
   `./build.sh` ([requirements and building](docs/upstream/requirements-and-building.md); the DXMT path also needs
   `./build.sh dxmt` before the layer step). Or download the DMG
   attached to a [release](https://github.com/StonkGuy/steamac/releases) (from v1.9-eac.1, built by GitHub Actions, ad-hoc signed). Copy
   **FX Steam Launcher.app** from `work/out/` (or the DMG) to Applications and open it (see *First open* below).
2. On first start, choose **Create New Disk…**. The app downloads Valve's SteamOS image, verifies it and sets it up.
   This takes a while, once.
3. Sign in to Steam in the window. Keep a **16:10** window size (Settings > Display > Default window
   size; the default, 1280×800, is 16:10). A 16:9 game in a 16:10 window is letterboxed.
4. Grant the **microphone** permission when macOS asks. Without it, the guest's audio capture fails repeatedly and games
   can stutter.
5. With **VRChat setup** enabled, sign in and confirm any tool downloads in Steam. Lite prepares FEX, Proton Experimental, EAC and VRChat launch options, then restarts Steam once. Install and launch VRChat yourself when ready. See [the setup flow](docs/vrchat-setup.ja.md).

### First open

The fork's builds are ad-hoc signed and not notarized, so macOS Gatekeeper blocks the first open. This is needed once:

- Right-click (or Control-click) the app in Applications, choose **Open**, then **Open** again; or
- if macOS 15 or newer does not offer that, open System Settings > Privacy & Security, scroll to the "FX Steam Launcher
  was blocked" message, click **Open Anyway** and confirm; or
- in Terminal: `xattr -dr com.apple.quarantine "/Applications/FX Steam Launcher.app"`.

## Choosing the graphics path

Settings > Advanced > **Allow DXMT (D3D11 on the Mac's Metal)**: on is the DXMT path, off the Vulkan path; it applies
from the next start. Nothing to set per game: when Steam starts, every installed Proton gets DXMT, and Proton puts it
into each game's prefix (Settings > Games can additionally give a game a profile; one that selects DXMT moves a game
without a compatibility tool of its own to Proton 10.0, since DXMT needs an x86-64 Proton). Turning it off restores
Proton's own files exactly. If Proton's original files are missing (for
example after switching between two builds of the app on one disk), the files stay DXMT's and the boot log says so;
repair Proton in Steam: the Proton tool > Properties > Installed Files > **Verify integrity of tool files**. DXMT
covers Direct3D 11 (and 10); play Direct3D 12 games on the Vulkan path (DXMT's Direct3D 12 is limited). EAC on DXMT is
verified with VRChat; if EAC fails in another game, turn **Allow DXMT** off.

| use | when |
|---|---|
| **DXMT** | Direct3D 11/10 games that render correctly on it. Measured faster on every title we could compare (see [docs/eac-performance.md](docs/eac-performance.md)) |
| **Vulkan** | Direct3D 12 games; games that use D3D11 stream output (geometry-shader or vertex-shader stream output with rasterization, for example Unigine Superposition, which shows black shadow areas on DXMT); any game that fails or looks wrong on DXMT |

The **Metal Performance HUD** shows the frame rate on either path: Settings > Display, the View menu, or Ctrl+Cmd+P. It can
be turned on and off while a game runs.

## Easy Anti-Cheat

EAC runs inside SteamOS under Valve's FEX emulator. This fork's patched FEX passes EAC's checks for VRChat, and for
Mini Royale (EAC `301`; that game was not played past its account prompt). Results differ from game to game: each title
ships its own EAC build and checks, so an untested game may or may not work. Lite.4 offers **VRChat setup** during first-run disk selection and in Settings > General. It installs the bundled,
pinned FEX after Valve's base tool is ready, chooses Proton Experimental only for VRChat, and writes the EAC launch
options with a CPU topology matching the VM. Steam supplies the tool downloads; sign-in and any installation dialogs
are user actions. Existing custom settings are preserved unless the user selects replacement, and originals are backed
up. Steam restarts once after preparation; VRChat is never started by the helper.

The [manual instructions](fex-eac/README.md) remain available for developer builds and recovery.
- **Expected:** EAC's launcher reports `Launcher finished with: 301, 'Easy Anti-Cheat successfully loaded in-game'` and
  the game logs `AntiCheat Session Begin: Success`.
- **Not expected to work:** anti-cheat that refuses virtual machines, and titles whose anti-cheat uses its own
  anti-debug checks beyond EAC's Linux module.
- **After a Steam update:** if Steam updates its FEX tool, it replaces the patched build. Run
  `sh install-fex-tool.sh` again.

## Troubleshooting

| symptom | what to do |
|---|---|
| the DXMT setting seems to have no effect | the setting applies at the next VM start: restart the VM after changing it. If the app lacks the DXMT host library, Settings says so and the app uses Vulkan (boot log: `gpu: graphics path Vulkan`) |
| EAC fails on DXMT | turn **Allow DXMT** off and restart the launcher |
| Direct3D 11 games fail on *Vulkan* after using DXMT | Proton still has DXMT's files: in Steam, the Proton tool > Properties > Installed Files > Verify integrity of tool files |
| EAC does not finish, or fails after a Steam update | the patched FEX is missing or was replaced by Valve's; run `sh install-fex-tool.sh status` |
| about a minute's stall before joining | check that `WINE_CPU_TOPOLOGY` is in the launch options |
| stutter with audio crackle | grant the microphone permission (System Settings > Privacy & Security > Microphone) |
| long first launch | shaders compile once per game and path; later launches are faster |

More: [docs/eac-troubleshooting.md](docs/eac-troubleshooting.md).

## Memory

The VM's memory is set in Settings > Advanced > **Memory** (automatic: half of the Mac's RAM, 4-16 GB). The Mac's GPU
memory comes from the same RAM, so a larger VM leaves less for macOS and the game's graphics. Memory the guest no longer
uses goes back to the Mac:

| mechanism | what it does | default | measured (M2, 16 GB, 8 GiB VM) |
|---|---|---|---|
| free page reporting (libkrun patch 0026) | pages the guest frees leave the VM's memory footprint on the Mac at once (stock libkrun keeps them charged on macOS) | on | idle after boot 0.7-0.8 GiB lower |
| boot page-cache trim (`steamac-mem-trim`) | 150 s after boot the guest drops its clean page cache once, so it is reported free too; runs once per boot, nothing during play | on; `steamac.mem_trim=0` on the kernel command line turns it off | idle VM footprint 8.92 -> 7.39 GiB |
| after-game trim (`steamac-mem-trim-games`) | when the last running game ends (or is killed), the guest drops its clean page cache and compacts free memory, so what the game used is reported free in whole 2 MiB blocks; a check every 10 s, nothing during play | on; `steamac.mem_trim=0` turns it off | after an OOM-killed VRChat, compacting took the VM footprint from 13 to 8.5 GiB |
| DXMT arena trim (`wmtr/`, libkrun patch 0028) | DXMT path: shared buffers idle for 1 s beyond a 128 MiB reserve go back to the Mac after a loading peak | on; `WMTR_ARENA_KEEP_MB`, `WMTR_ARENA_TRIM_MS`, `-1` keeps all | offline test: 504 -> 203 MiB after a peak; live check pending |
| DXMT objects of an ended game (`wmtr/`) | when a game exits or is killed, the Metal objects it still owned (textures, buffers, pipelines) are released at once; before, they stayed in the VM until it shut down | on | after an OOM-killed VRChat ~1.1 GiB of graphics memory stayed behind; offline test, live check pending |

Swap inside the guest: zram as large as the VM's memory, compressed with zstd (SteamOS's own is half the RAM with
lzo-rle), and behind it a swap file on /home of half the VM's memory that only takes pages once zram is full
(`steamac.swap_fallback=0` turns the file off and removes it). With SteamOS's zram alone, a heavy VRChat world change in
an 8 GiB VM filled RAM and zram and the guest kernel killed the game.

Scope: general (any game on this stack). These lower the idle and after-load footprint; they do not make a game fit
whose peak needs more than the VM and the Mac have (see *Limits*).

## Limits

- One machine verified (M2, 16 GB, macOS 27.0). VRChat is verified in game on both paths; Mini Royale's EAC launcher
  reaches `301` (not played further). Other titles are untested and results differ game by game.
- 16 GB Macs: heavy titles can exceed the memory available. Unigine Superposition (720p, Low) went past 14 GB of app
  memory on both paths with an 8 GiB VM.
- VR (Meta Quest 3 over WiVRn or Virtual Desktop) is experimental and off by default: see [docs/vr.md](docs/vr.md).
- DXMT: Direct3D 11/10. Its Direct3D 12 is limited (feature level 11_1, DXBC only, no DXIL, no ray tracing;
  ExecuteIndirect stalls the GPU); use *Vulkan* for Direct3D 12 games.
- DXMT: Direct3D 11 stream output with rasterization or from a geometry shader is not implemented upstream; such games
  render wrong on DXMT (Unigine Superposition: black shadow areas). Use *Vulkan* for them.
- D3DMetal is not included.
- The DXMT setting applies to every game; on it the game's Metal layer covers the whole VM view (a windowed game or alt-tab
  shows the game layer).
- Games that need more memory than the VM gets (Settings > Advanced) will swap.
- Turning **Allow DXMT** on or off changes every installed Proton at the next boot; see *Choosing the graphics path* for
  the repair if a Proton was left with DXMT's files.
- KosmicKrisp compiles pipelines on a thread pool and waits at their first use (fxgl/steamac's series;
  `MESA_KK_COMPILE_THREADS` sets the pool size). This fork's earlier opt-in variant is parked in
  `host/kosmickrisp/patches-fork-pending/`.
- The microphone has had little testing; a freeze after a microphone start is not fully ruled out. A rebuilt or re-signed
  app asks again for microphone permission.

## Documentation

| page | contents |
|---|---|
| [SETUP.md](SETUP.md) | the full setup guide: install, graphics path, Easy Anti-Cheat, troubleshooting |
| [docs/fork.md](docs/fork.md) | what changed in this fork and its status |
| [docs/eac-how-it-works.md](docs/eac-how-it-works.md) | the EAC chain and why the FEX swap is needed |
| [docs/eac-performance.md](docs/eac-performance.md) | measurements and limits |
| [docs/vr.md](docs/vr.md) | VR with a Quest 3 over WiVRn or Virtual Desktop (experimental): setup, pairing, options, limits |
| [fex-eac/README.md](fex-eac/README.md) | patched FEX setup and launch options |
| [docs/upstream/README.md](docs/upstream/README.md) | upstream steamac's documentation (Apache-2.0, © FX GAMES FZ LLC) |

## Support this fork

steamac Lite will continue to be available for free. If this fork helps you, you can [support r-fallingstar through GitHub Sponsors](https://github.com/sponsors/r-fallingstar) to help cover development and testing costs.

Sponsorship supports r-fallingstar's improvements, testing, and maintenance of this fork. It is optional and does not include individual support or guaranteed feature requests.

## Licences and attributions

| component | licence |
|---|---|
| steamac (this fork) | Apache-2.0, © FX GAMES FZ LLC and contributors (`LICENSE`, `NOTICE`) |
| patched FEX ([StonkGuy/FEX](https://github.com/StonkGuy/FEX/tree/eac-2610), built by `fex-eac/build-fex.sh`) | MIT, as FEX-Emu |
| DXMT, with this fork's patches (`host/dxmt/patches/`) | LGPL-2.1 |
| wmtr (the DXMT remoting layer, `wmtr/`) | BSD-3-Clause |
| libkrun and its patches | Apache-2.0 |
| virglrenderer, Mesa / KosmicKrisp | MIT |
| MoltenVK | Apache-2.0 |
| DXVK (zlib), Proton / Wine (LGPL-2.1 and others) | per upstream; installed by Steam, not shipped |
| Linux kernel derivatives | GPL-2.0-only; complete source for each release is attached to it |

**D3DMetal is not bundled.** The app ships no game files and no EAC binaries. EAC comes from Valve's Proton EasyAntiCheat Runtime,
installed by Steam.

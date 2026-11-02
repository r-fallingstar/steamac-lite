# Bundled FEX runtime

The optional **VRChat setup / VRChat向け設定** uses this prebuilt Linux aarch64
runtime, so an 8 GB Mac does not have to compile FEX during setup.

- Source: https://github.com/StonkGuy/FEX/tree/6effd2384085818345ec32e6abb4181c7135a9a7
- Tag: `eac-2610.5`; clean source tree, recursive submodules from that commit.
- Built with `../build-fex.sh` in the SteamOS ARM64 guest on Apple M1, one job.
- Release, Steam support, no thunks/tests/config GUI/LTO; `TUNE_CPU=native` (Apple M1).
- The SHA-256 of every installed file and the archive is in `manifest.json`.
- `scripts/lite/verify-fex-runtime.py` verifies the archive and license copies.
- Original source and dependency notices are in `licenses/` and in the archive.

The archive contains only the staged runtime and license texts. It contains no
Steam account, disk image, game, Proton or Easy Anti-Cheat download. The setup
waits for Valve's FEX Steam tool to finish downloading, backs up its ten original
files, and applies only those ten files with Steam and all games stopped.

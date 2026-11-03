# SteamAC Lite online installer

A separate ARM64 macOS application for the BOOTH download. It fetches this repository's release list and selects the newest published, numbered `-lite.N` release with an uploaded ARM64 DMG, SHA-256 digest and size. Drafts and unrelated release channels are ignored.

The installer verifies the DMG and app signature, bundle identifier and version. Only the app is installed. Existing SteamOS disks and preferences are never opened. A current or newer installed app is kept. A running app is not stopped automatically. The installed app starts only when the user chooses **Open SteamAC Lite**.

Build and package from a clean checkout:

```sh
bash scripts/installer/build.sh
python3 scripts/installer/package.py
```

Output is under `work/installer/`. The ZIP contains the small installer, instructions, Apache license notices and links to matching source. The full app is downloaded from GitHub; its own license notices and corresponding modified library sources remain with that release.

The build links only Apple system frameworks, is signed ad hoc and is not notarized. It requires Apple Silicon and macOS 15.5 or later. No GitHub authentication or persistent service is used. Cookies and app/user identifiers are not sent; the installer version is in User-Agent.

Tests:

```sh
python3 scripts/test/network-installer.py
bash scripts/installer/build.sh test
```

Only the test build accepts `STEAMAC_INSTALLER_TEST_DESTINATION` and `STEAMAC_INSTALLER_TEST_FEED`. Its Open button cannot launch the main app. Production packaging rejects test builds and test hooks. Use an isolated folder for GUI download/install checks, then remove the disposable app. Do not run the VM for installer verification.

# GitHub Pages guide

The published files are `docs/index.html`, `docs/en/index.html`, `docs/ko/index.html` and `docs/zh-CN/index.html`.

Edit `guide.template.html` and the four JSON files in `locales/`. Then run:

```sh
python3 scripts/site/build-guide-annotations.py
python3 scripts/site/build-guide.py
python3 scripts/site/build-guide.py --check
node scripts/test/guide-language.cjs
```

All languages must contain the same keys. The build stops on a missing translation. Downloads, section IDs and styles are shared. Screenshots are selected per language through `screenshots.json`; the build validates every asset and reads its dimensions.

The root Japanese page checks an explicit `?lang=` choice, the saved preference and then supported browser languages. Other language URLs always display the requested language. The Japanese link uses `?lang=ja` so it also works when storage is blocked. Without JavaScript, each page and the language links still work. Language changes preserve the current section.

Chinese uses Simplified Chinese. The Korean guide uses the app’s Korean menu labels from Lite.7. App and Steam screenshots were captured from Lite.8 in each page’s language. GitHub and Finder keep their original UI and have translated annotations. The guide covers the Lite.8 app and detects the current Mac input source independently of display language and physical keyboard geometry.

Gemini 3.8 Flash High reviewed all four locale files in Antigravity on November 3, 2026. Chinese UI labels were aligned with the app (通用, VRChat 专用设置, 新建磁盘…) and the Korean Steam settings wording was made consistent.

## Screenshots

`docs/media/guide/{ja,en,ko,zh-CN}/` contains each language’s app and installation scenes. Settings and disk creation are real window captures from the installed Lite.8 app, using isolated preferences and `--selftest-settings`. Steam was photographed in a disposable clone with `english`, `japanese`, `koreana` and `schinese` selected; VRChat was not launched. The original VM and preferences were retained.

`build-guide-annotations.py` wraps the original captures in `shared/` with translated headings and callouts as SVG. It does not replace UI text. Finder follows the Mac’s language and GitHub labels remain English. Run its `--check` option to detect stale annotations. Captions, alternative text and annotation text were reviewed with Gemini 3.8 Flash High on November 3, 2026.

## Link previews

Each language has a 1200×630 JPEG in `docs/media/social/`. The artwork uses the homepage colors, typography and Steam screenshot. Open Graph and X metadata point to the corresponding language's image.

Run `python3 scripts/site/build-share-cards.py` to prepare the HTML artwork in `work/share-cards/`. Serve the repository root locally, render each page in a 1200×630 browser viewport and export its JPEG to `docs/media/social/guide-<locale>-v2.jpg`. Change the filename version when replacing an image to avoid reusing an old image URL. Rebuild the guides after updating the metadata or artwork paths.

## Access analytics

All four guide pages include the Cloudflare Web Analytics snippet from the shared template. Only the guide pages load it; the app and other repository documentation do not. The beacon token is a public ingestion identifier, not an account credential. Reports are available to the owner in Cloudflare under Observability → Analytics → Web Analytics → `r-fallingstar.github.io`. No public visitor counter is displayed. Collection starts after installation and does not include earlier visits.

## BOOTH online installer

The `#booth` subsection is an alternative to the manual DMG install. It links to the free product and continues at `#language`, skipping the manual copy step. Each locale has real `installer-ready.jpg` and `installer-done.jpg` window captures from the 1.0.0 installer with Lite.9. A disposable installation in `~/Applications` was used; the installed app was never opened and was removed after capture. The normal app in `/Applications`, SteamOS disk and preferences were retained. Screenshots use each page's display language.

The Release Assets and Finder captures in `shared/` now show Lite.9. `build-guide-annotations.py` adds translated instructions around those unmodified captures. The direct download links and file labels also target Lite.9.

The project display name is `steamac Lite`. Legacy release asset filenames, existing app bundle paths and bundle identifiers are retained for updater compatibility. Historical window captures show the names in the published Lite.9 build.

## Lite.12 installation prompt captures

The `dmg-install` scene now uses `media/guide/{ja,en,ko,zh-CN}/install-and-open-lite12.png`. Each image shows the native **Install and Open** alert in that page’s language, including both buttons. The portrait figure displays the whole window rather than cropping it into the old Finder ratio.

`scripts/site/capture-dmg-install.swift` is the capture entry point. Compile it as main.swift with the unmodified `DmgInstall.swift`, `InstallerCore.swift` and `UpdateInstallSupport.swift` from tag `v1.9.4-lite.12` (commit `22553c7c10aa3b6458605823cfa6310437949a5a`). The isolated capture bundle uses the published app’s localization resources and icon, a different bundle ID and no VM code. Run it on a read-only disk image with `-AppleLanguages '(ja)'`, `(en)`, `(ko)` or `(zh-Hans)` and `STEAMAC_GUIDE_CAPTURE=/absolute/output.png`. It renders the native AppKit frame onto the native window background and exits without installing or opening the app. This captures the app’s controls directly, so neither a mouse pointer nor a computer-use cursor is included.

The annotation builder now maintains only the GitHub download scene. The earlier Finder SVGs are historical captures and are no longer referenced by the guide.

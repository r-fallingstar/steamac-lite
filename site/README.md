# GitHub Pages guide

The published files are `docs/index.html`, `docs/en/index.html`, `docs/ko/index.html` and `docs/zh-CN/index.html`.

Edit `guide.template.html` and the four JSON files in `locales/`. Then run:

```sh
python3 scripts/site/build-guide.py
python3 scripts/site/build-guide.py --check
node scripts/test/guide-language.cjs
```

All languages must contain the same keys. The build stops on a missing translation. Images, downloads, section IDs and styles are shared.

The root Japanese page checks an explicit `?lang=` choice, the saved preference and then supported browser languages. Other language URLs always display the requested language. The Japanese link uses `?lang=ja` so it also works when storage is blocked. Without JavaScript, each page and the language links still work. Language changes preserve the current section.

Chinese uses Simplified Chinese. The Korean guide explains that the app itself has no Korean UI and uses English menu labels. Screenshots remain in Japanese. This update changes the guide only.

Gemini 3.8 Flash High reviewed all four locale files in Antigravity on November 3, 2026. Chinese UI labels were aligned with the app (通用, VRChat 专用设置, 新建磁盘…) and the Korean Steam settings wording was made consistent.

## Link previews

Each language has a 1200×630 JPEG in `docs/media/social/`. The artwork uses the homepage colors, typography and Steam screenshot. Open Graph and X metadata point to the corresponding language's image.

Run `python3 scripts/site/build-share-cards.py` to prepare the HTML artwork in `work/share-cards/`. Serve the repository root locally, render each page in a 1200×630 browser viewport and export its JPEG to `docs/media/social/guide-<locale>-v1.jpg`. Change the filename version when replacing an image to avoid reusing an old image URL. Rebuild the guides after updating the metadata or artwork paths.

## Access analytics

All four guide pages include the Cloudflare Web Analytics snippet from the shared template. Only the guide pages load it; the app and other repository documentation do not. The beacon token is a public ingestion identifier, not an account credential. Reports are available to the owner in Cloudflare under Observability → Analytics → Web Analytics → `r-fallingstar.github.io`. No public visitor counter is displayed. Collection starts after installation and does not include earlier visits.

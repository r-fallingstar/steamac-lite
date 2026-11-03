#!/usr/bin/env python3
"""Prepare 1200×630 HTML artwork for browser export to docs/media/social/*.jpg."""
from pathlib import Path
import html
import json

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT/'work/share-cards'
OUT.mkdir(parents=True,exist_ok=True)
style = '''
* { box-sizing: border-box; }
html, body { margin: 0; width: 1200px; height: 630px; overflow: hidden; }
body { background: #fbd6ec; color: #493050; font-family: "Avenir Next", "Hiragino Kaku Gothic ProN", "Apple SD Gothic Neo", "PingFang SC", sans-serif; }
.arc { position: absolute; width: 850px; height: 850px; top: -110px; right: -305px; border-radius: 50%; background: #d9bdf4; }
.copy { position: absolute; top: 66px; left: 64px; width: 550px; }
.eyebrow { display: inline-block; margin: 0 0 30px; padding: 8px 16px; border: 1px solid #f0c5df; border-radius: 7px; background: white; color: #b92d77; box-shadow: 4px 4px 0 #db98c0; font-size: 17px; font-weight: 700; }
h1 { margin: 0; font-size: 70px; font-weight: 800; line-height: 1.12; letter-spacing: -2px; color: #c53782; paint-order: stroke fill; -webkit-text-stroke: 5px white; text-shadow: 3px 4px 0 #ae78b435; white-space: nowrap; }
h2 { margin: 16px 0 25px; font-size: 57px; font-weight: 800; line-height: 1.25; color: #7950b5; paint-order: stroke fill; -webkit-text-stroke: 4px white; }
.description { margin: 0; max-width: 510px; font-size: 20px; line-height: 1.8; color: #67446a; }
.requirements { position: absolute; left: 64px; bottom: 90px; margin: 0; padding: 10px 18px; border: 2px solid white; border-radius: 24px; background: #fff0f8; color: #744596; font-size: 18px; font-weight: 600; }
.address { position: absolute; bottom: 35px; left: 64px; margin: 0; color: #73556f; font-size: 17px; }
.photo { position: absolute; left: 660px; top: 145px; width: 510px; height: 347px; padding: 9px; margin: 0; border: 2px solid white; border-radius: 25px; background: #fffafd; box-shadow: 10px 10px 0 #ac7bc42e; transform: rotate(2deg); }
.photo img { width: 100%; height: 100%; display: block; object-fit: cover; object-position: top; border-radius: 15px; }
html:lang(ko) .copy, html:lang(zh-Hans) .copy { font-family: "Apple SD Gothic Neo", "PingFang SC", sans-serif; }
html:lang(ko) .description { word-break: keep-all; }
'''
for locale,lang in [('ja','ja'),('en','en'),('ko','ko'),('zh-CN','zh-Hans')]:
    copy = json.loads((ROOT/f'site/locales/{locale}.json').read_text())
    text = lambda key:html.escape(copy[key])
    page = f'''<!doctype html><html lang="{lang}" translate="no"><head><meta charset="utf-8"><meta name="google" content="notranslate"><title>{text('page.title1')} — share card</title><style>{style}</style></head><body>
<div class="arc"></div><main class="copy"><p class="eyebrow">{text('top.p1')}</p><h1>SteamAC Lite</h1><h2>{text('hero-title.span1')}</h2><p class="description">{text('top.p2')}</p></main>
<figure class="photo"><img src="../../docs/media/guide/{locale}/steam-ready.jpg" alt="{text('attr.alt1')}"></figure>
<p class="requirements">Apple Silicon · RAM 8 GB+</p><p class="address">r-fallingstar.github.io/steamac-lite</p>
</body></html>'''
    (OUT/f'{locale}.html').write_text(page)
print('Share card artwork:', OUT)

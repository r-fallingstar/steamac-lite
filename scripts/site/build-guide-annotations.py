#!/usr/bin/env python3
"""Add translated instructions around unmodified GitHub captures as SVG assets."""
import argparse
import base64
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--check', action='store_true')
args = parser.parse_args()
shared = ROOT/'docs/media/guide/shared'
release = base64.b64encode((shared/'release-assets-lite9.png').read_bytes()).decode()
font = '&quot;Avenir Next&quot;,&quot;Hiragino Kaku Gothic ProN&quot;,&quot;Apple SD Gothic Neo&quot;,&quot;Malgun Gothic&quot;,&quot;PingFang SC&quot;,sans-serif'
for locale,lang in [('ja','ja'),('en','en'),('ko','ko'),('zh-CN','zh-Hans')]:
    copy = json.loads((ROOT/f'site/locales/{locale}.json').read_text())
    text = lambda key: html.escape(copy[key])
    for scene,kind,height in [('release-download','download',640)]:
        heading, note = text(f'photo.{kind}-title'), text(f'photo.{kind}-note')
        content = f'''<image x="32" y="108" width="1216" height="360" href="data:image/png;base64,{release}"/>
<rect x="32" y="299" width="1216" height="47" rx="6" fill="none" stroke="#b92d77" stroke-width="4"/>
<text x="32" y="577" font-size="22">{note}</text>'''
        svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="{height}" viewBox="0 0 1280 {height}" xml:lang="{lang}">
<title>{heading}</title><desc>{note}</desc>
<rect width="1280" height="{height}" fill="white"/><rect width="1280" height="88" fill="#fff0f8"/>
<g font-family="{font}" fill="#493050"><text x="32" y="58" font-size="32" font-weight="700">{heading}</text>
{content}</g></svg>
'''
        destination = ROOT/f'docs/media/guide/{locale}/{scene}.svg'
        destination.parent.mkdir(exist_ok=True)
        if args.check:
            assert destination.read_text() == svg, ('Outdated annotation',destination)
        else:
            destination.write_text(svg)
        print(('Checked: ' if args.check else 'Built: ')+str(destination.relative_to(ROOT)))

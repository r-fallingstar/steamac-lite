#!/usr/bin/env python3
"""Build the four static GitHub Pages guides. Run --check to verify generated files."""
import argparse
import html
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import struct
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
SITE = 'https://r-fallingstar.github.io/steamac-lite/'
LANGUAGES = {'ja':('日本語','ja',''), 'en':('English','en','en/'),
             'ko':('한국어','ko','ko/'), 'zh-CN':('简体中文','zh-Hans','zh-CN/')}
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--check', action='store_true')
args = parser.parse_args()
template = (ROOT/'site/guide.template.html').read_text()
source = json.loads((ROOT/'site/locales/ja.json').read_text())
screenshots = json.loads((ROOT/'site/screenshots.json').read_text())
assert set(screenshots) == set(LANGUAGES), 'Every guide language needs screenshots'

def image_size(path):
    data = path.read_bytes()
    if path.suffix == '.svg':
        svg = ET.fromstring(data)
        return int(svg.attrib['width']), int(svg.attrib['height'])
    if data.startswith(b'\x89PNG\r\n\x1a\n'):
        return struct.unpack('>II', data[16:24])
    assert data.startswith(b'\xff\xd8'), ('Unsupported image', path)
    pos = 2
    while pos < len(data):
        assert data[pos] == 0xff, ('Invalid JPEG', path)
        while data[pos] == 0xff:
            pos += 1
        marker = data[pos]
        pos += 1
        size = int.from_bytes(data[pos:pos+2], 'big')
        if marker in {0xc0, 0xc1, 0xc2, 0xc3, 0xc5, 0xc6, 0xc7, 0xc9, 0xca, 0xcb, 0xcd, 0xce, 0xcf}:
            height, width = struct.unpack('>HH', data[pos+3:pos+7])
            return width, height
        assert size >= 2, ('Invalid JPEG segment', path)
        pos += size
    raise AssertionError(('Missing image dimensions', path))

class Fragment(HTMLParser):
    def handle_starttag(self, tag, attrs):
        assert tag in {'a','strong','span','kbd','br'}, ('unexpected translation markup', tag)
        for name,value in attrs:
            assert name in {'href','class','aria-hidden'}, ('unexpected attribute', name)
            if name == 'href':
                assert value.startswith(('https://github.com/r-fallingstar/steamac-lite/',
                                         'https://support.apple.com/')), ('unexpected link', value)

for locale,(name,language,path) in LANGUAGES.items():
    copy = json.loads((ROOT/f'site/locales/{locale}.json').read_text())
    assert set(copy) == set(source), (locale, 'missing or extra translation keys')
    for key,value in copy.items():
        assert isinstance(value,str) and value.strip(), (locale,key,'empty translation')
        Fragment().feed(value)
    prefix = '../' if path else ''
    assert set(screenshots[locale]) == {'steam-ready', 'release-download', 'dmg-install',
                                       'create-disk', 'vrchat-settings', 'display-settings',
                                       'installer-ready', 'installer-done'}
    images = {}
    for scene, asset in screenshots[locale].items():
        assert asset.startswith(f'media/guide/{locale}/') and '..' not in asset
        width, height = image_size(ROOT/'docs'/asset)
        images.update({f'image.{scene}.src':prefix+asset, f'image.{scene}.width':str(width),
                       f'image.{scene}.height':str(height)})
    alternatives = '\n'.join(f'<link rel="alternate" hreflang="{code}" href="{SITE}{route}">'
                             for code,(_,_,route) in LANGUAGES.items())
    alternatives += f'\n<link rel="alternate" hreflang="x-default" href="{SITE}">'
    links = []
    for code,(label,tag,route) in LANGUAGES.items():
        target = prefix+route if route else prefix+'?lang=ja'
        current = ' aria-current="page"' if code == locale else ''
        links.append(f'<a href="{target}" lang="{tag}" hreflang="{code}" data-language="{code}"{current}>{label}</a>')
    label = html.escape(copy['language.label'],quote=True)
    selector = (f'<details class="language-picker"><summary aria-label="{label}: {name}">{name}</summary>'
                f'<nav aria-label="{label}">'+''.join(links)+'</nav></details>')
    values = {**copy, **images, 'html_lang':language, 'root_prefix':prefix,
              'canonical':SITE+path, 'alternates':alternatives,'language_selector':selector,
              'og_image':SITE+f'media/social/guide-{locale}-v2.jpg'}
    def substitute(match):
        key = match[1]
        assert key in values, ('unknown template key',key)
        return html.escape(values[key],quote=True) if key.startswith(('attr.','photo.','image.')) else values[key]
    page = re.sub(r'@@([\w.-]+)@@',substitute,template)
    # Asset URLs also occur inside translated HTML fragments.
    page = page.replace('src="media/','src="'+prefix+'media/').replace('href="media/','href="'+prefix+'media/')
    assert '@@' not in page
    destination = ROOT/'docs'/path/'index.html'
    if args.check:
        assert destination.read_text() == page, f'Outdated generated page: {destination}'
    else:
        destination.parent.mkdir(parents=True,exist_ok=True)
        destination.write_text(page)
    print(('Checked' if args.check else 'Built')+': '+str(destination.relative_to(ROOT)))

#!/usr/bin/env python3
"""Build the four static GitHub Pages guides. Run --check to verify generated files."""
import argparse
import html
from html.parser import HTMLParser
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
SITE = 'https://r-fallingstar.github.io/steamac-lite/'
LANGUAGES = {'ja':('日本語','ja',''), 'en':('English','en','en/'),
             'ko':('한국어','ko','ko/'), 'zh-CN':('简体中文','zh-Hans','zh-CN/')}
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--check', action='store_true')
args = parser.parse_args()
template = (ROOT/'site/guide.template.html').read_text()
source = json.loads((ROOT/'site/locales/ja.json').read_text())

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
    values = {**copy, 'html_lang':language, 'root_prefix':prefix,
              'canonical':SITE+path, 'alternates':alternatives,'language_selector':selector,
              'og_image':SITE+f'media/social/guide-{locale}-v1.jpg'}
    def substitute(match):
        key = match[1]
        assert key in values, ('unknown template key',key)
        return html.escape(values[key],quote=True) if key.startswith(('attr.','photo.')) else values[key]
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

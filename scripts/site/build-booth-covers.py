#!/usr/bin/env python3
"""Render source HTML for the three localized square BOOTH gallery images."""
from pathlib import Path
import html,json,re
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'work/booth-covers';OUT.mkdir(parents=True,exist_ok=True)
source=(ROOT/'site/booth/cover.html').read_text()
copy=json.loads((ROOT/'site/booth/covers.json').read_text())
for locale,text in copy.items():
    escape=lambda key:html.escape(text[key])
    page=source.replace('lang="ja"','lang="'+text['language']+'"',1)
    page=re.sub(r'<title>.*?</title>','<title>SteamAC Lite — '+locale+' BOOTH cover</title>',page,count=1)
    for tag,cls,key in [('p','eyebrow','eyebrow'),('p','description','description'),('p','requirements','requirements')]:
        page=re.sub(f'<{tag} class="{cls}">.*?</{tag}>',f'<{tag} class="{cls}">'+escape(key)+f'</{tag}>',page,count=1)
    page=re.sub(r'<h2>.*?</h2>','<h2>'+escape('subtitle')+'</h2>',page,count=1)
    page=page.replace('../../docs/media/guide/ja/steam-ready.jpg',f'../../docs/media/guide/{locale}/steam-ready.jpg')
    page=re.sub(r'(<img[^>]*alt=")[^"]*(")',lambda m:m[1]+escape('image_alt')+m[2],page,count=1)
    page=page.replace('</style>','''
body {position:relative;}
.description {font-size:26px;line-height:1.6;}
.requirements {top:412px;}
.photo {top:480px;}
html:lang(ko) .copy {font-family:"Apple SD Gothic Neo","Malgun Gothic",sans-serif;}
html:lang(zh-Hans) .copy {font-family:"PingFang SC","Microsoft YaHei",sans-serif;}
</style>''')
    (OUT/f'{locale}.html').write_text(page)
    print('Built:',locale)

#!/usr/bin/env python3
"""Package the verified GitHub DMG and its notices for the free BOOTH download."""
from pathlib import Path
import hashlib,json,zipfile
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'work/booth-release';OUT.mkdir(parents=True,exist_ok=True)
record=json.loads((ROOT/'work/dist/distribution-validation.json').read_text())
version=record['version'];dmg=ROOT/'work/dist'/record['dmg']
assert hashlib.file_digest(dmg.open('rb'),'sha256').hexdigest()==record['sha256']
assert all(record[k] for k in ['dmg_integrity_verified','copied_out_signature_verified','copied_out_keyboard_selftest_passed'])
files={dmg.name:dmg,'Quick-Start-ja.txt':ROOT/'docs/quick-start.ja.md','LICENSE.txt':ROOT/'LICENSE','NOTICE.txt':ROOT/'NOTICE','libkrun-lite.6-sources.tar.gz':ROOT/'work/dist/libkrun-lite.6-sources.tar.gz'}
licenses=Path('/Applications/SteamAC Lite.app/Contents/Resources/licenses')
assert (licenses/'THIRD-PARTY-NOTICES.txt').is_file()
for p in licenses.rglob('*'):
 if p.is_file():files['licenses/'+str(p.relative_to(licenses))]=p
links=('SteamAC Lite '+version+'\n\nGuide: https://r-fallingstar.github.io/steamac-lite/?lang=ja\n'
       'Fork source (matching app commit): https://github.com/r-fallingstar/steamac-lite/tree/'+record['source_commit']+'\n'
       'Release and verification records: https://github.com/r-fallingstar/steamac-lite/releases/tag/v'+version+'\n'
       'Upstream: https://github.com/StonkGuy/steamac\n'
       'Upstream releases and corresponding GPL/LGPL source archives: https://github.com/StonkGuy/steamac/releases\n'
       'Component source locations and license texts: licenses/THIRD-PARTY-NOTICES.txt\n\n'
       'The DMG is byte-for-byte identical to the GitHub release.\n'
       'No SteamOS disk, Steam account data, or game files are included.\n')
(OUT/'Sources-and-Links.txt').write_text(links)
files['Sources-and-Links.txt']=OUT/'Sources-and-Links.txt'
sums=[]
for name,p in files.items():
 with p.open('rb') as stream:sums.append(hashlib.file_digest(stream,'sha256').hexdigest()+'  '+name)
(OUT/'SHA256SUMS.txt').write_text('\n'.join(sums)+'\n');files['SHA256SUMS.txt']=OUT/'SHA256SUMS.txt'
archive=OUT/f'SteamAC-Lite-{version}-macos-arm64-booth.zip'
with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_STORED) as z:
 for name,p in files.items():z.write(p,'SteamAC-Lite-'+version+'/'+name)
with zipfile.ZipFile(archive) as z:
 assert z.testzip() is None
 actual=hashlib.sha256(z.read('SteamAC-Lite-'+version+'/'+dmg.name)).hexdigest()
 assert actual==record['sha256']
result=dict(archive=archive.name,bytes=archive.stat().st_size,sha256=hashlib.file_digest(archive.open('rb'),'sha256').hexdigest(),dmg_sha256=actual,files=len(files),version=version,steam_account_data_included=False)
(OUT/'package-validation.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))

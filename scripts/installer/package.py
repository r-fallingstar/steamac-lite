#!/usr/bin/env python3
"""Distribute the small installer, rather than a fixed app release, on BOOTH."""
from pathlib import Path
import hashlib,json,os,plistlib,subprocess,zipfile
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'work/installer';APP=OUT/'Install SteamAC Lite.app'
info=plistlib.loads((APP/'Contents/Info.plist').read_bytes());assert info['InstallerTestBuild'] is False
version=info['CFBundleShortVersionString'];env={**os.environ,'DEVELOPER_DIR':'/Library/Developer/CommandLineTools'}
commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,env=env,text=True).strip()
assert info['InstallerSourceCommit']==commit
assert not subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,env=env).strip(),'Commit the source first'
subprocess.run(['codesign','--verify','--deep','--strict',str(APP)],check=True)
binary=(APP/'Contents/MacOS/steamac-installer').read_bytes()
assert b'STEAMAC_INSTALLER_TEST_FEED' not in binary and b'STEAMAC_INSTALLER_TEST_DESTINATION' not in binary and b'open suppressed in installer tests' not in binary
notice='''steamac Lite Online Installer

日本語
Install SteamAC Lite.appを開き、「インストール」を押すとGitHubから最新版を取得します。
完了後に「steamac Liteを開く」を押して初期設定を進めてください。
すでに最新版が入っている場合はダウンロードしません。
SteamOSのディスクと設定は引き継ぎます。通信環境が必要です。
https://r-fallingstar.github.io/steamac-lite/?lang=ja

English
Open Install SteamAC Lite.app and choose Install to get the latest app from GitHub.
When it finishes, choose Open steamac Lite to continue setup.
Your SteamOS disk and settings are kept. Internet access is required.
https://r-fallingstar.github.io/steamac-lite/en/

한국어
Install SteamAC Lite.app을 열고 “설치”를 누르면 GitHub에서 최신 앱을 다운로드합니다.
완료되면 “steamac Lite 열기”를 눌러 초기 설정을 진행하세요.
SteamOS 디스크와 설정은 유지됩니다. 인터넷 연결이 필요합니다.
https://r-fallingstar.github.io/steamac-lite/ko/

简体中文
打开 Install SteamAC Lite.app，点击「安装」即可从 GitHub 获取最新版应用。
完成后点击「打开 steamac Lite」继续初始设置。
SteamOS 磁盘和设置会保留，需要互联网连接。
https://r-fallingstar.github.io/steamac-lite/zh-CN/
'''
(OUT/'はじめに.txt').write_text(notice)
(OUT/'Sources-and-Links.txt').write_text('Installer source: https://github.com/r-fallingstar/steamac-lite/tree/'+commit+'/host/installer\nApp releases: https://github.com/r-fallingstar/steamac-lite/releases\nGuide: https://r-fallingstar.github.io/steamac-lite/\nLicense: Apache-2.0; see LICENSE.txt and NOTICE.txt.\nThe downloaded app includes its component license notices; corresponding modified library source is attached to its release.\n')
archive=OUT/f'SteamAC-Lite-Installer-{version}-macos-arm64.zip'
files={str(p.relative_to(OUT)):p for p in APP.rglob('*') if p.is_file()}
files.update({'はじめに.txt':OUT/'はじめに.txt','Sources-and-Links.txt':OUT/'Sources-and-Links.txt','LICENSE.txt':ROOT/'LICENSE','NOTICE.txt':ROOT/'NOTICE'})
with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
 for name,path in sorted(files.items()):z.write(path,'SteamAC-Lite-Online-Installer/'+name)
with zipfile.ZipFile(archive) as z:
 assert z.testzip() is None
 executable=z.getinfo('SteamAC-Lite-Online-Installer/Install SteamAC Lite.app/Contents/MacOS/steamac-installer')
 assert (executable.external_attr>>16)&0o111
result={'type':'online-installer','version':version,'source_commit':commit,'archive':archive.name,'bytes':archive.stat().st_size,'sha256':hashlib.file_digest(archive.open('rb'),'sha256').hexdigest(),'signed_ad_hoc':True,'notarized':False,'app_binaries_or_game_data_included':False,'languages':['ja','en','ko','zh-Hans','ru']}
(OUT/'package-validation.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

#!/usr/bin/env python3
"""Exercise startup update notices in the real app without booting SteamOS."""
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import datetime,json,os,plistlib,subprocess,sys,tempfile,threading,time,uuid
ROOT=Path(__file__).resolve().parents[2]
APP=Path(sys.argv[1]) if len(sys.argv)>1 else ROOT/'work/out/SteamAC Lite.app'
DOMAIN='steamac.lite.startup-test.'+uuid.uuid4().hex
ENV={**os.environ,'DEVELOPER_DIR':'/Library/Developer/CommandLineTools','STEAMAC_DEFAULTS_DOMAIN':DOMAIN,'STEAMAC_SENTRY':'0'}
version=plistlib.loads((APP/'Contents/Info.plist').read_bytes())['CFBundleShortVersionString'];name=f'SteamAC-Lite-{version}-macos-arm64.dmg'
fixture=[{'tag_name':'v'+version,'draft':False,'prerelease':True,'assets':[{'name':name,'state':'uploaded','size':100,'digest':'sha256:'+'a'*64,'browser_download_url':f'https://github.com/r-fallingstar/steamac-lite/releases/download/v{version}/{name}'}]}]
class Handler(BaseHTTPRequestHandler):
    requests=0
    status=200
    def do_GET(self):
        Handler.requests+=1
        if Handler.status==503:
            self.send_response(503);self.end_headers();return
        if self.headers.get('If-None-Match')=='"startup-test"':
            self.send_response(304);self.end_headers();return
        self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('ETag','"startup-test"');self.end_headers();self.wfile.write(json.dumps(fixture).encode())
    def log_message(self,*args):pass
server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
threading.Thread(target=server.serve_forever,daemon=True).start()
ENV['STEAMAC_UPDATE_URL']=f'http://127.0.0.1:{server.server_port}/releases'
try:
    with tempfile.TemporaryDirectory(prefix='startup-update-test-',dir=ROOT/'work') as td:
        root=Path(td);ENV['STEAMAC_GAME_STATS_FILE']=str(root/'stats.json')
        prefs=root/'settings.plist';prefs.write_bytes(plistlib.dumps({'checkForUpdates':True,'updateLastCheck':datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None),'applicationLanguage':'ja','shareGameStats':False}))
        subprocess.run(['defaults','import',DOMAIN,str(prefs)],check=True,capture_output=True)
        def run(case,current,expected,*,notice,fetch=True):
            before=Handler.requests;log=root/(case+'.log')
            with log.open('w') as output:
                process=subprocess.Popen([str(APP/'Contents/MacOS/steamac-vm'),'--preview-startup-update'],env={**ENV,'STEAMAC_FAKE_VERSION':current},stdout=output,stderr=output)
                try:
                    deadline=time.monotonic()+12
                    while time.monotonic()<deadline:
                        content=log.read_text()
                        if expected in content:break
                        if process.poll() is not None:raise AssertionError(case+': app exited: '+content)
                        time.sleep(.1)
                    else:raise AssertionError(case+': missing outcome: '+log.read_text())
                    time.sleep(.2);content=log.read_text()
                    assert ('showing the update window' in content)==notice,(case,content)
                    assert (Handler.requests>before)==fetch,(case,'network request count')
                    assert 'vm: starting' not in content
                finally:
                    process.terminate()
                    try:process.wait(timeout=5)
                    except subprocess.TimeoutExpired:process.kill();process.wait()
            print(case+': PASS',flush=True)
        run('recent-check-still-notifies','1.9.8-lite.1','showing the update window',notice=True)
        run('second-launch-uses-304-and-notifies','1.9.8-lite.1','showing the update window',notice=True)
        subprocess.run(['defaults','write',DOMAIN,'updateSkippedVersion','-string',version],check=True)
        run('skipped-version-stays-skipped','1.9.8-lite.1','skipped by the user',notice=False)
        run('current-version-stays-quiet',version,'update: up to date',notice=False)
        subprocess.run(['defaults','write',DOMAIN,'checkForUpdates','-bool','false'],check=True)
        run('automatic-check-opt-out',version,'startup check off',notice=False,fetch=False)
        subprocess.run(['defaults','write',DOMAIN,'checkForUpdates','-bool','true'],check=True)
        Handler.status=503
        run('network-failure-stays-quiet','1.9.8-lite.1','update: check failed',notice=False)
        print('startup update: PASS (6 cases; no VM or download started)',flush=True)
finally:
    server.shutdown();server.server_close()
    subprocess.run(['defaults','delete',DOMAIN],capture_output=True)

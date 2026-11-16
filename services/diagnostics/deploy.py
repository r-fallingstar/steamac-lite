#!/usr/bin/env python3
"""Deploy intake + private inbox. Requires Wrangler login, local Git credential, PyNaCl.

No GitHub credential is copied to Cloudflare or to an app. The generated queue
reader token is stored as a Worker secret and an encrypted GitHub Actions secret.
"""
from pathlib import Path
import argparse
import base64
import json
import os
import re
import secrets
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from nacl.public import PublicKey, SealedBox

ROOT = Path(__file__).resolve().parents[2]
SERVICE = Path(__file__).resolve().parent
OUT = ROOT / 'work/diagnostics-deployment'
OUT.mkdir(exist_ok=True)
parser = argparse.ArgumentParser()
parser.add_argument('--wrangler', required=True)
args = parser.parse_args()
env = {**os.environ, 'CI': 'true', 'DEVELOPER_DIR': '/Library/Developer/CommandLineTools', 'GIT_TERMINAL_PROMPT': '0'}
config = json.loads((ROOT / 'scripts/lite/diagnostics.json').read_text())
repo = config['inbox']
assert re.fullmatch(r'r-fallingstar/[a-z0-9-]+', repo)
credential = subprocess.run(['git', 'credential', 'fill'], cwd=ROOT, env=env,
    input='protocol=https\nhost=github.com\n\n', text=True, capture_output=True, check=True)
token = dict(s.split('=', 1) for s in credential.stdout.splitlines() if '=' in s).get('password')
assert token, 'GitHub credential unavailable'


def github(method, path, body=None):
    req = urllib.request.Request('https://api.github.com' + path,
        data=None if body is None else json.dumps(body).encode(), method=method, headers={
            'Authorization': 'Bearer ' + token, 'Accept': 'application/vnd.github+json',
            'Content-Type': 'application/json', 'User-Agent': 'steamac-private-diagnostics-setup',
            'X-GitHub-Api-Version': '2022-11-28'})
    with urllib.request.urlopen(req, timeout=40) as response:
        data = response.read()
        return json.loads(data) if data else None


def wrangler(*command, stdin=None):
    p = subprocess.run([args.wrangler, *command], cwd=SERVICE, env=env, input=stdin,
        text=True, capture_output=True)
    if p.returncode:
        # Wrangler output does not echo secret-put's stdin; still avoid printing it here.
        (OUT / 'last-command-error.txt').write_text(p.stdout + p.stderr)
        raise RuntimeError('Wrangler failed: ' + ' '.join(command[:3]) + '; see local last-command-error.txt')
    return p.stdout


metadata = github('GET', '/repos/' + repo)
assert metadata['private'] and metadata['owner']['login'] == 'r-fallingstar'
databases = json.loads(wrangler('d1', 'list', '--json'))
database = next((d for d in databases if d['name'] == 'steamac-lite-diagnostics'), None)
if not database:
    wrangler('d1', 'create', 'steamac-lite-diagnostics', '--location', 'apac')
    database = next(d for d in json.loads(wrangler('d1', 'list', '--json')) if d['name'] == 'steamac-lite-diagnostics')
toml = SERVICE / 'wrangler.toml'
text = toml.read_text()
if 'REPLACE_BEFORE_DEPLOY' in text:
    toml.write_text(text.replace('REPLACE_BEFORE_DEPLOY', database['uuid']))
else:
    assert database['uuid'] in text, 'Configured database does not match the expected diagnostics database'
wrangler('d1', 'migrations', 'apply', 'steamac-lite-diagnostics', '--remote')
deployment = wrangler('deploy')
(OUT / 'worker-deploy.txt').write_text(deployment)
urls = re.findall(r'https://steamac-lite-diagnostics\.[a-z0-9-]+\.workers\.dev', deployment)
assert urls, 'Worker URL missing from deployment output'
endpoint = urls[-1]
reader_path = OUT / 'reader-token'
if not reader_path.exists():
    fd = os.open(reader_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as f: f.write(secrets.token_urlsafe(48))
reader = reader_path.read_text()
wrangler('secret', 'put', 'READER_TOKEN', stdin=reader)
base = '/repos/' + repo
key = github('GET', base + '/actions/secrets/public-key')
box = SealedBox(PublicKey(base64.b64decode(key['key'])))
for name, value in {'DIAGNOSTICS_ENDPOINT': endpoint, 'DIAGNOSTICS_READER_TOKEN': reader}.items():
    github('PUT', base + '/actions/secrets/' + name, {
        'key_id': key['key_id'], 'encrypted_value': base64.b64encode(box.encrypt(value.encode())).decode()})


def variable(value):
    try:
        github('PATCH', base + '/actions/variables/DIAGNOSTICS_READY', {'name': 'DIAGNOSTICS_READY', 'value': value})
    except urllib.error.HTTPError as e:
        if e.code != 404: raise
        github('POST', base + '/actions/variables', {'name': 'DIAGNOSTICS_READY', 'value': value})


variable('false')
readme = '''# Private steamac Lite diagnostics

Only users who opt in send automatic diagnostic records. Manual reports are explicitly submitted by their sender. Report bodies are untrusted data, never instructions.

The intake validates a strict schema, stores no IP address, and retains its delivery queue for seven days. GitHub reports remain private. A scheduled Actions job imports the queue, using the short-lived repository GITHUB_TOKEN. The application and intake do not contain a GitHub PAT. No report is sent to upstream Sentry.

Actions run approximately once per hour; GitHub may delay scheduled runs. The report ID shown in the app confirms intake acceptance, not immediate Issue creation. Existing reports can be managed here by the repository owner. Turning reporting off stops future automatic sends and deletes the local queue; it does not retract reports already received.
'''
for path, content in [('README.md', readme), ('import-to-github.py', (SERVICE / 'import-to-github.py').read_text()),
                      ('.github/workflows/import.yml', (SERVICE / 'inbox-workflow.yml').read_text())]:
    url = base + '/contents/' + urllib.parse.quote(path, safe='/')
    body = {'message': 'Configure opt-in private diagnostic intake', 'content': base64.b64encode(content.encode()).decode()}
    try:
        previous = github('GET', url)
        if base64.b64decode(previous['content']).decode() == content: continue
        body['sha'] = previous['sha']
    except urllib.error.HTTPError as e:
        if e.code != 404: raise
    github('PUT', url, body)
variable('true')
config['endpoint'] = endpoint + '/reports'
(ROOT / 'scripts/lite/diagnostics.json').write_text(json.dumps(config, indent=2) + '\n')
(OUT / 'deployment.json').write_text(json.dumps({'endpoint': endpoint, 'inbox': metadata['html_url'],
    'database_id': database['uuid'], 'github_credential_copied': False}, indent=2) + '\n')
print('Intake:', endpoint)
print('Private inbox:', metadata['html_url'])

#!/usr/bin/python3
"""Read-only, post-exit VRChat evidence for a diagnostic clone.

Run as root before the diagnostic runner starts its tests. JSON records on stdout
are labelled CAMERA_STARTUP/source=collect_boot; the runner routes stdout to the
local journal/serial console. No uploads, output files, environment requests,
process inspection, hooks, game launches, settings changes, or image access.

Limits: two newest output_log_*.txt, first 1 MiB + last 2 MiB each (overlap
removed), 120 selected/context lines per file, 1200 characters per line. Context
is one line either side, and must itself be diagnostic or a stack frame. Directory
scans stop at 4096 entries. Metadata reads are at most 64 KiB per file (version
4 KiB, config_info 256 KiB). Previous-boot user journal: 240 entries, 256 KiB,
3 seconds, 60 selected exit lines. Missing evidence is reported, never repaired.
"""

import argparse
from datetime import datetime
import errno
import hashlib
import io
import json
import os
from pathlib import Path
import re
import selectors
import stat
import subprocess
import sys
import time


STEAM = Path('/home/steamos/.local/share/Steam')
MIB = 1024 * 1024
HEAD_BYTES, TAIL_BYTES = MIB, 2 * MIB
LINE_LIMIT, LINE_CHARS = 120, 1200
SCAN_LIMIT = 4096
META_BYTES = 64 * 1024
JOURNAL_BYTES, JOURNAL_ENTRIES, JOURNAL_LINES = 256 * 1024, 240, 60
JOURNAL_SECONDS = 3
PREFIX = 'CAMERA_STARTUP '

# These are deliberately generic diagnostic terms, not a list of known errors.
RELEVANT = re.compile(
    r'\b(?:start(?:up|ing|ed)?|initializ\w*|launch\w*|loading|loaded|world|'
    r'join\w*|connect\w*|disconnect\w*|error\w*|fail\w*|time[ -]?out\w*|'
    r'exception\w*|graphics|renderer|rendering|direct3d\w*|d3d\w*|dxvk|'
    r'vulkan|unity|proton|wine|video|camera\w*|webcam\w*|selfie|mediapipe|'
    r'capture\w*|quartz|qcap|avicap|gstreamer|mfplat|shutdown|exiting|'
    r'elapsed|duration)\b', re.I)
PRIVATE = re.compile(
    r'chat(?:box|message|\s+message|\s+text)?|\b(?:message|text|content|body)\s*[:=]|'
    r'\b(?:whisper|conversation|friend\w*|invite\w*|notification\w*|'
    r'display[ _-]?name|username|player[ _-]?name|bio|password|'
    r'user|player|avatar|account|profile|authenticated)\b|'
    r'\b(?:onplayer\w*|onuser\w*|player\s+(?:joined|left)|'
    r'user\s+(?:joined|left)|received\s+message)\b', re.I)
# "VRChat" itself is not private chat text.
STACK = re.compile(r'^\s*(?:at\s+[\w.$+`<>]+\s*\(|(?:UnityEngine|System)\.[\w.]+[:(])')
URL = re.compile(r'\b[a-z][a-z0-9+.-]*://[^\s<>"\']+', re.I)
IDS = re.compile(
    r'\b(?:usr|wrld|avtr|grp|file|inst|user|auth)_[a-z0-9_-]+(?::[^\s<>"\']*)?|'
    r'\bSTEAM_\d:[01]:\d+\b|\[U:\d:\d+\]|\b\d{15,20}\b|'
    r'\b[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}\b', re.I)
SECRET = re.compile(
    r'\b(?:authorization|proxy-authorization|bearer|cookie|set-cookie|'
    r'[\w-]*(?:token|secret|session[_-]?id|api[_-]?key|authcookie)[\w-]*)'
    r'\b\s*(?::|=|\s)\s*.*', re.I)
QUOTED = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'')
TOOL_PATH = re.compile(
    r'(?:steamapps/common/(?:Proton - Experimental|Proton [0-9][A-Za-z0-9 ._-]{0,48})|'
    r'compatibilitytools\.d/[Pp]roton-[Rr][Tt][Ss][Pp][A-Za-z0-9._-]{0,64})'
    r'(?:/files)?(?=/|[\s"\']|$)')


def sanitize(line):
    """Pure filter: return a redacted diagnostic line, or None for private text.

    Never emit unfiltered neighbour lines. Quotes, structured payloads, instance
    identities, addresses, home paths and credentials are not diagnostic evidence.
    """
    line = str(line)
    stamp = re.match(r'^\[?\d{4}[.-]\d{2}[.-]\d{2} \d{2}:\d{2}:\d{2}(?:\.\d+)?\]?', line)
    timestamp = stamp[0] if stamp else ''
    if timestamp:
        line = line[len(timestamp):]
    # Remove the product name only for privacy classification (chat != VRChat).
    if PRIVATE.search(IDS.sub('[id]', re.sub('vrchat', '', line, flags=re.I))):
        return None
    line = re.sub(r'[\x00-\x1f\x7f-\x9f\u202a-\u202e\u2066-\u2069]', ' ', line)
    line = URL.sub('[url]', line)
    line = SECRET.sub('[credential omitted]', line)
    line = IDS.sub('[id]', line)
    line = re.sub(r'\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b', '[email]', line, flags=re.I)
    line = re.sub(r'(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?::\d+)?\b', '[address]', line)
    line = re.sub(r'(?<!\w)(?:[0-9a-f]{0,4}:){2,}[0-9a-f:]{0,39}(?:%\w+)?', '[address]', line, flags=re.I)
    line = re.sub(r'(?i)(?:[a-z]:[\\/]|/(?:home|Users)/)[^\s<>"\']+', '[path]', line)
    line = QUOTED.sub('[quoted]', line)
    # JSON/request bodies and arbitrary values attached to personal/world names.
    line = re.sub(r'[\{].*', '[payload omitted]', line)
    line = re.sub(r'(?i)\b(?:world\s*name|room\s*name|entering\s+room|'
                  r'(?:loading|loaded|joining)\s+(?:world|room)|world|room|user|owner|author|account|name)\s*[:=]\s*.*',
                  '[name/value omitted]', line)
    line = re.sub(r'(?i)\b(?:joining|entering)\s+(?:world|room)\s+(?!\[id\])[^\r\n]+',
                  'joining world [destination omitted]', line)
    line = re.sub(r'(?<![\w])[A-Za-z0-9_+/=-]{32,}(?![\w])', '[opaque]', line)
    return (timestamp + ' ' + line.strip()).strip()[:LINE_CHARS] or None


def emit(out, kind, **values):
    record = dict(source='collect_boot', kind=kind, **values)
    out.write(PREFIX + json.dumps(record, ensure_ascii=True, sort_keys=True) + '\n')
    out.flush()


def error_name(error):
    # Exception messages can contain paths/private values; emit the errno only.
    return errno.errorcode.get(getattr(error, 'errno', None), type(error).__name__)


def open_read(path):
    # O_NOATIME keeps root's diagnostic reads from updating guest file atimes.
    flags = os.O_RDONLY | os.O_NONBLOCK | getattr(os, 'O_CLOEXEC', 0)
    flags |= getattr(os, 'O_NOATIME', 0)
    fd = os.open(path, flags)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise OSError(errno.EINVAL, 'not a regular file')
        return os.fdopen(fd, 'rb')
    except BaseException:
        os.close(fd)
        raise


def metadata(path, limit):
    with open_read(path) as stream:
        info = os.fstat(stream.fileno())
        data = stream.read(min(info.st_size, limit))
    complete = len(data) == info.st_size
    result = dict(size=info.st_size, mtime_ns=info.st_mtime_ns,
                  bytes_read=len(data), complete=complete)
    result['sha256' if complete else 'prefix_sha256'] = hashlib.sha256(data).hexdigest()
    return result, data


def safe_version(data):
    # Version labels only; never print arbitrary file contents or extra lines.
    value = data.decode('utf-8', 'replace').strip()
    if len(value) <= 160 and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9 ._+()/-]*', value) and not re.search(r'\d{15,}', value):
        return value
    return '[non-version text omitted]'


def collect_prefix(steam, out):
    compat = steam / 'steamapps/compatdata/438100'
    for name, limit in (('version', 4096), ('config_info', 256 * 1024)):
        try:
            result, data = metadata(compat / name, limit)
            if name == 'version':
                result['version'] = safe_version(data)
            else:
                selected = []
                for number, line in enumerate(data.decode('utf-8', 'replace').splitlines(), 1):
                    for match in TOOL_PATH.finditer(line):
                        selected.append(dict(line=number, tool_path='<Steam>/' + match.group(0)))
                        if len(selected) >= 12:
                            break
                    if len(selected) >= 12:
                        break
                result['selected_tool_path_lines'] = selected
            emit(out, 'compatdata', file=name, **result)
        except OSError as error:
            emit(out, 'compatdata', file=name, status=error_name(error))
    for name in ('pfx', 'pfx/creation_sync_guard'):
        try:
            info = (compat / name).stat()
            emit(out, 'prefix_mtime', file=name, mtime_ns=info.st_mtime_ns)
        except OSError as error:
            emit(out, 'prefix_mtime', file=name, status=error_name(error))


def limited_entries(directory):
    with os.scandir(directory) as entries:
        for count, entry in enumerate(entries):
            if count == SCAN_LIMIT:
                return
            yield entry


def collect_tools(steam, out):
    tools = [('stock', steam / 'steamapps/common/Proton - Experimental')]
    try:
        candidates = sorted(entry.name for entry in limited_entries(steam / 'compatibilitytools.d')
                            if re.fullmatch(r'(?i)proton-rtsp[A-Za-z0-9._-]{0,64}', entry.name))
        tools.extend(('rtsp-' + str(index), steam / 'compatibilitytools.d' / name)
                     for index, name in enumerate(candidates[:4], 1))
        emit(out, 'tool_scan', rtsp_matches=len(candidates), rtsp_limit=4, directory_entry_limit=SCAN_LIMIT)
    except OSError as error:
        emit(out, 'tool_scan', status=error_name(error))
    for label, tool in tools:
        for name in ('version', 'toolmanifest.vdf', 'compatibilitytool.vdf', '.steamac-camera-verified-source'):
            try:
                result, data = metadata(tool / name, 4096 if name == 'version' else META_BYTES)
                if name == 'version':
                    result['version'] = safe_version(data)
                elif name == '.steamac-camera-verified-source':
                    value = data.decode('ascii', 'replace').strip()
                    if re.fullmatch(r'[0-9a-f]{64}', value):
                        result['archive_sha256'] = value
                else:
                    # VDF values can include install paths/identities: retain only
                    # a few known manifest fields and strictly safe scalar values.
                    fields = {}
                    for key, value in re.findall(r'"([^"\n]+)"\s*"([^"\n]*)"', data.decode('utf-8', 'replace')):
                        if key.lower() in ('display_name', 'version', 'priority', 'require_tool_appid',
                                           'from_oslist', 'to_oslist', 'compatmanager_layer_name'):
                            if re.fullmatch(r'[A-Za-z0-9 ._+()-]{0,120}', value) and not re.search(r'\d{15,}', value):
                                fields[key.lower()] = value
                    result['fields'] = fields
                emit(out, 'tool_metadata', tool=label, tool_path='<Steam>/' + str(tool.relative_to(steam)), file=name, **result)
            except OSError as error:
                emit(out, 'tool_metadata', tool=label, file=name, status=error_name(error))


def read_windows(path):
    """Return disjoint, complete-line byte windows; offsets are file offsets."""
    with open_read(path) as stream:
        info = os.fstat(stream.fileno())
        size = info.st_size
        ranges = [(0, min(size, HEAD_BYTES))]
        if size > HEAD_BYTES:
            ranges.append((max(HEAD_BYTES, size - TAIL_BYTES), size))
        # Merge touching ranges so small files are read once, without a false gap.
        if len(ranges) == 2 and ranges[0][1] == ranges[1][0]:
            ranges = [(0, size)]
        windows = []
        for start, end in ranges:
            stream.seek(start)
            data = stream.read(end - start)
            offset = start
            if start:
                cut = data.find(b'\n')
                if cut < 0:
                    continue
                offset += cut + 1
                data = data[cut + 1:]
            if end < size:
                cut = data.rfind(b'\n')
                data = data[:cut + 1] if cut >= 0 else b''
            windows.append((offset, data))
    return info, windows


def select_lines(windows, limit=LINE_LIMIT):
    selected = []
    for window, (start, data) in enumerate(windows):
        lines = []
        offset = start
        for raw in data.splitlines(keepends=True):
            # Overlong payloads are not evidence; don't match fragments of them.
            text = raw.decode('utf-8', 'replace').rstrip('\r\n')
            clean = sanitize(text) if len(raw) <= 16 * 1024 else None
            lines.append((offset, text, clean))
            offset += len(raw)
        hits = {index for index, (_, text, clean) in enumerate(lines)
                if clean and RELEVANT.search(text)}
        included = set(hits)
        for index in hits:
            for neighbour in (index - 1, index + 1):
                if 0 <= neighbour < len(lines):
                    _, text, clean = lines[neighbour]
                    if clean and STACK.search(text):
                        included.add(neighbour)
        for index in sorted(included):
            offset, _, clean = lines[index]
            selected.append(dict(window=window, byte_offset=offset,
                                 context=index not in hits, text=clean))
    # Keep both early startup and the last failure if the selection is large.
    total = len(selected)
    if total > limit:
        selected = selected[:limit // 2] + selected[-(limit - limit // 2):]
    return selected, total


def collect_logs(steam, out):
    directory = steam / 'steamapps/compatdata/438100/pfx/drive_c/users/steamuser/AppData/LocalLow/VRChat/VRChat'
    newest = []
    try:
        for entry in limited_entries(directory):
            if not re.fullmatch(r'output_log_[A-Za-z0-9_.-]+\.txt', entry.name):
                continue
            try:
                info = entry.stat(follow_symlinks=False)
                if stat.S_ISREG(info.st_mode):
                    newest.append((info.st_mtime_ns, entry.name))
                    newest = sorted(newest, reverse=True)[:2]
            except OSError:
                continue
    except OSError as error:
        emit(out, 'logs', status=error_name(error))
        return
    emit(out, 'logs', files=len(newest), order='newest mtime first', directory_entry_limit=SCAN_LIMIT)
    for rank, (_, name) in enumerate(newest, 1):
        # Labels deliberately omit filenames (which need not be privacy-safe).
        label = 'latest-' + str(rank)
        try:
            info, windows = read_windows(directory / name)
            selected, total = select_lines(windows)
            emit(out, 'log_file', file=label, size=info.st_size, mtime_ns=info.st_mtime_ns,
                 windows=[dict(byte_offset=start, bytes=len(data)) for start, data in windows],
                 head_limit=HEAD_BYTES, tail_limit=TAIL_BYTES, line_limit=LINE_LIMIT,
                 selected_before_limit=total, emitted=len(selected), line_char_limit=LINE_CHARS)
            for line in selected:
                emit(out, 'log_line', file=label, **line)
        except OSError as error:
            emit(out, 'log_file', file=label, status=error_name(error))


def collect_timings(steam, out):
    """Only numeric timing history, without messages or destination identities."""
    directory = steam/'steamapps/compatdata/438100/pfx/drive_c/users/steamuser/AppData/LocalLow/VRChat/VRChat'
    try:
        paths = []
        for entry in limited_entries(directory):
            if re.fullmatch(r'output_log_[A-Za-z0-9_.-]+\.txt',entry.name):
                info = entry.stat(follow_symlinks=False)
                if stat.S_ISREG(info.st_mode):
                    paths.append((info.st_mtime_ns, directory/entry.name))
        paths = sorted(paths,reverse=True)[:12]
    except OSError as error:
        emit(out,'timing_history',status=error_name(error))
        return
    for index, (_,path) in enumerate(paths,1):
        try:
            info,windows = read_windows(path)
            first = finished = last = None
            world_ms = download_ms = None
            for _,data in windows:
                for raw in data.splitlines():
                    text = raw.decode('utf-8','replace')
                    match = re.match(r'^(\d{4}\.\d{2}\.\d{2} \d{2}:\d{2}:\d{2})',text)
                    stamp = datetime.strptime(match[1],'%Y.%m.%d %H:%M:%S') if match else None
                    if stamp:
                        first = first or stamp
                        last = stamp
                    if finished is None and 'Finished entering world.' in text:
                        finished = stamp
                    if world_ms is None:
                        number = re.search(r'World loading took ([\d,.]+)ms',text)
                        if number: world_ms = float(number[1].replace(',',''))
                    if download_ms is None:
                        number = re.search(r'World download took ([\d,.]+)ms',text)
                        if number: download_ms = float(number[1].replace(',',''))
            emit(out,'timing_history',file='history-'+str(index),mtime_ns=info.st_mtime_ns,
                 first_log_time=first.isoformat() if first else None,
                 first_world_complete=finished.isoformat() if finished else None,
                 client_log_to_world_seconds=(finished-first).total_seconds() if first and finished else None,
                 observed_log_seconds=(last-first).total_seconds() if first and last else None,
                 first_world_loading_ms=world_ms,first_world_download_ms=download_ms,
                 note='First client log to first completed world; excludes Steam/Proton pre-launch work. Local log timezone unchanged.')
        except (OSError,ValueError) as error:
            emit(out,'timing_history',file='history-'+str(index),status=error_name(error))


def collect_steam_launches(steam,out):
    """Small, game-specific Steam launch records for full-startup comparisons."""
    for name in ('gameprocess_log.txt','console_log.txt','console-linux.txt'):
        try:
            info,windows = read_windows(steam/'logs'/name)
            selected=[]
            for _,data in windows:
                for raw in data.splitlines():
                    if len(raw)>16384:continue
                    text=raw.decode('utf-8','replace')
                    if '438100' not in text or not any(word in text for word in ('GameAction','LaunchApp','Adding process','Removing process','Game process','GameAction')):continue
                    clean=sanitize(text)
                    if clean:selected.append(clean)
            for text in selected[-60:]:
                emit(out,'steam_launch',file=name,text=text)
        except OSError as error:
            emit(out,'steam_launch_file',file=name,status=error_name(error))


def journal_read():
    """Bound both subprocess lifetime and bytes; never collect the whole journal."""
    command = ['/usr/bin/journalctl', '--boot=-1', '--no-pager', '--output=json',
               '--lines=' + str(JOURNAL_ENTRIES), '_UID=1000']
    with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                          env={'PATH': '/usr/bin:/bin', 'LC_ALL': 'C', 'SYSTEMD_PAGER': 'cat'}) as child:
        data = bytearray()
        reason = 'complete'
        deadline = time.monotonic() + JOURNAL_SECONDS
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(child.stdout, selectors.EVENT_READ)
                while True:
                    left = deadline - time.monotonic()
                    if left <= 0:
                        reason = 'timeout'
                        break
                    if not selector.select(left):
                        reason = 'timeout'
                        break
                    block = os.read(child.stdout.fileno(), min(16384, JOURNAL_BYTES - len(data)))
                    if not block:
                        break
                    data.extend(block)
                    if len(data) >= JOURNAL_BYTES:
                        reason = 'byte_limit'
                        break
        finally:
            if child.poll() is None:
                child.kill()
            child.wait()
        return bytes(data), reason, child.returncode


def collect_journal(out):
    try:
        data, reason, code = journal_read()
    except OSError as error:
        emit(out, 'previous_boot_user_journal', status=error_name(error))
        return
    records = []
    for raw in data.splitlines():
        try:
            item = json.loads(raw)
        except (ValueError, UnicodeError):
            continue
        message = item.get('MESSAGE') if isinstance(item, dict) else None
        if not isinstance(message, str) or len(message) > 16 * 1024:
            continue
        if not re.search(r'VRChat|438100|proton|wine|app-steam', message, re.I):
            continue
        if not re.search(r'exit|stopp|terminat|fail|timeout|timed out|crash|killed|remov.*process', message, re.I):
            continue
        clean = sanitize(message)
        if clean:
            stamp = str(item.get('__REALTIME_TIMESTAMP', ''))
            records.append(dict(timestamp_us=stamp if re.fullmatch(r'\d{1,20}', stamp) else None, text=clean))
    emit(out, 'previous_boot_user_journal', boot=-1, status=reason, returncode=code,
         bytes_read=len(data), byte_limit=JOURNAL_BYTES, entry_limit=JOURNAL_ENTRIES,
         seconds_limit=JOURNAL_SECONDS, line_limit=JOURNAL_LINES,
         note='Last persisted boot, user 1000 only; absence is not proof of a clean exit.')
    for record in records[-JOURNAL_LINES:]:
        emit(out, 'previous_boot_exit', **record)


def collect_snapshot(out):
    # These are current guest-wide counters, NOT memory at the time of Joining.
    for name in ('meminfo', 'pressure/memory', 'pressure/cpu', 'pressure/io'):
        try:
            with open_read(Path('/proc') / name) as stream:
                data = stream.read(8192).decode('ascii', 'replace')
            values = []
            for line in data.splitlines():
                if name == 'meminfo':
                    if re.fullmatch(r'(?:MemTotal|MemFree|MemAvailable|Buffers|Cached|SwapTotal|SwapFree|'
                                    r'Active|Inactive|AnonPages|Mapped|Shmem|Slab|SReclaimable|PageTables):\s+\d+ kB', line):
                        values.append(line)
                elif re.fullmatch(r'(?:some|full) avg10=\d+\.\d+ avg60=\d+\.\d+ avg300=\d+\.\d+ total=\d+', line):
                    values.append(line)
            emit(out, 'current_guest_snapshot', file='/proc/' + name, values=values,
                 timing='post-game collection boot snapshot; not the previous game stall')
        except OSError as error:
            emit(out, 'current_guest_snapshot', file='/proc/' + name, status=error_name(error))


def collect_boot(steam=STEAM, out=None, *, journal=False, snapshot=True, log_excerpts=False):
    """Runner entry point. Reads only fixed metadata/logs; accepts no environment."""
    out = sys.stdout if out is None else out
    steam = Path(steam)
    emit(out, 'begin', timestamp_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
         root=os.geteuid() == 0, destination='local stdout for runner journal/serial',
         scope='normal post-exit game logs and metadata; no live process access')
    collect_prefix(steam, out)
    collect_tools(steam, out)
    if log_excerpts:
        collect_logs(steam, out)
    collect_timings(steam, out)
    collect_steam_launches(steam, out)
    if journal:
        collect_journal(out)
    if snapshot:
        collect_snapshot(out)
    emit(out, 'end')


def self_test():
    """Pure in-memory fixtures: safe to run on the host without collecting it."""
    fixtures = [
        ('Joining world wrld_12345678-abcd-1234-abcd-123456789012:42~private(usr_1234) https://example.invalid/a?token=secret',
         ('wrld_', 'usr_', 'example.invalid', 'secret'), False),
        ('Error SteamID=76561198012345678 STEAM_0:1:123456 [U:1:123456] user_id=usr_abcd',
         ('76561198012345678', 'STEAM_0', '[U:1', 'usr_abcd'), False),
        ('Timeout Authorization: Bearer super-secret', ('super-secret',), False),
        ('Exception token=short-value', ('short-value',), False),
        ('Camera failure for "Private Identity" at C:\\users\\Alice\\file.txt alice@example.invalid',
         ('Private Identity', 'Alice', 'example.invalid'), False),
        ('[ChatBox] camera error: private conversation', (), True),
        ('[VRChat] OnPlayerJoined PrivateName', (), True),
        ('[VRChat] Message: camera error private text', (), True),
        ('[VRChat] Startup completed in 12.34 seconds', (), False),
        ('Graphics device Vulkan initialized', (), False),
        ('Selfie camera timeout after 30 seconds', (), False),
    ]
    for line, secrets, omitted in fixtures:
        result = sanitize(line)
        assert (result is None) == omitted, (line, result)
        assert result is None or all(secret not in result for secret in secrets), (line, result)
    data = (b'[ChatBox] camera private text\n[VRChat] Startup completed\n'
            b'private neighbour Alice\nError graphics timeout\n at System.Exception()\n')
    lines, _ = select_lines([(0, data)])
    assert len(lines) == 3 and all('private' not in line['text'] for line in lines)
    lines, total = select_lines([(0, b'Camera timeout\n' * 200)])
    assert len(lines) == LINE_LIMIT and total == 200
    assert len(sanitize('Error ' + 'x' * 2000)) <= LINE_CHARS
    assert sanitize('2026.11.12 18:37:22 Debug - Camera initialized').startswith('2026.11.12 18:37:22')
    assert sanitize('[2026-11-12 19:12:34] GameAction [AppID 438100] : LaunchApp').startswith('[2026-11-12 19:12:34]')
    assert 'PrivateHome' not in sanitize('Loading world: PrivateHome')
    output = io.StringIO()
    emit(output, 'fixture', text='safe')
    assert json.loads(output.getvalue()[len(PREFIX):])['source'] == 'collect_boot'
    print('CAMERA_STARTUP_SELF_TEST ok (in-memory fixtures only)', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--self-test', action='store_true', help='pure fixtures only; collect nothing')
    parser.add_argument('--journal', action='store_true', help='optionally read bounded previous-boot user journal (default: skip)')
    parser.add_argument('--no-journal', action='store_true', help='explicitly skip previous-boot user journal')
    parser.add_argument('--log-excerpts', action='store_true', help='opt in to filtered local game-log excerpts; default is numeric timings/metadata only')
    parser.add_argument('--no-snapshot', action='store_true', help='skip current guest meminfo/PSI')
    args = parser.parse_args()
    if args.self_test:
        self_test()
    else:
        collect_boot(journal=args.journal and not args.no_journal, snapshot=not args.no_snapshot, log_excerpts=args.log_excerpts)


if __name__ == '__main__':
    main()

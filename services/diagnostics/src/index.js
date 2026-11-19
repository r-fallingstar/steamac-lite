// Anonymous, opt-in intake. GitHub writes happen in the private repository's
// Actions job with its short-lived GITHUB_TOKEN; no GitHub PAT lives here or in an app.
const UUID = /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/;
export const EVENTS = ['startup-stalled', 'app-unresponsive', 'launcher-crashed', 'previous-session-incomplete',
  'gpu-context-fatal', 'pipeline-compile-failed', 'rust-panic', 'provision-failed',
  'disk-creation-failed', 'vm-exited-unexpectedly', 'vm-killed', 'steamos-not-responding', 'manual'];
export const STAGES = ['launcher', 'main', 'install', 'language', 'settings', 'options', 'metal-cache',
  'crash-reporting', 'supervisor', 'first-run', 'vm-setup', 'window', 'permission', 'vm-start',
  'vm', 'provision', 'kernel', 'init', 'system', 'systemd', 'graphical', 'session', 'steam', 'steam-check',
  'steam-download', 'steam-install', 'steam-start', 'ready', 'shutdown'];
const KILL_REASONS = ['memory', 'code-signing', 'decryption', 'unspecified', 'unavailable'];
class Failure extends Error { constructor(status) { super('Request rejected'); this.status = status; } }
function check(ok, status = 400) { if (!ok) throw new Failure(status); }
function text(value, max, pattern) {
  check(typeof value === 'string' && value.length <= max && pattern.test(value)); return value;
}
function integer(value, min, max) { check(Number.isInteger(value) && value >= min && value <= max); return value; }
function exact(value, keys) {
  check(value && typeof value === 'object' && !Array.isArray(value));
  check(Object.keys(value).every(k => keys.includes(k)));
}
// Raw logs/stacks/paths are deliberately absent from automatic reports. Unknown
// fields fail rather than accidentally becoming telemetry after a client change.
export function validate(b) {
  exact(b, ['schema', 'id', 'kind', 'version', 'commit', 'macos', 'model', 'chip', 'ram_gb',
    'stage', 'elapsed_s', 'exit_code', 'signal', 'kill_reason', 'feedback']);
  check(b.schema === 1 && EVENTS.includes(b.kind) && STAGES.includes(b.stage));
  const r = { schema: 1, id: text(b.id, 36, UUID), kind: b.kind,
    version: text(b.version, 48, /^\d+\.\d+\.\d+-lite\.\d+$/),
    commit: text(b.commit, 40, /^[a-f0-9]{7,40}$/),
    macos: text(b.macos, 32, /^\d+\.\d+\.\d+$/),
    model: text(b.model, 40, /^(?:Mac(?:Book(?:Air|Pro)?|mini|Pro|Studio)?\d+,\d+|unknown)$/),
    chip: text(b.chip, 40, /^(?:Apple M\d+(?: (?:Pro|Max|Ultra))?|unknown)$/),
    ram_gb: integer(b.ram_gb, 1, 4096), stage: b.stage,
    elapsed_s: integer(b.elapsed_s, 0, 604800) };
  if (b.exit_code !== undefined) r.exit_code = integer(b.exit_code, 0, 255);
  if (b.signal !== undefined) r.signal = integer(b.signal, 1, 127);
  if (b.kill_reason !== undefined) {
    check(b.kind === 'vm-killed' && r.signal === 9 && r.exit_code === undefined && KILL_REASONS.includes(b.kill_reason));
    r.kill_reason = b.kill_reason;
  }
  if (b.kind === 'manual') {
    exact(b.feedback, ['message', 'email', 'launcher_log']);
    r.feedback = { message: text(b.feedback.message, 8000, /^[\s\S]{10,}$/),
      email: text(b.feedback.email, 254, /^(?:[^\s@]+@[^\s@]+\.[^\s@]+)?$/),
      launcher_log: text(b.feedback.launcher_log, 24000, /^[\s\S]*$/) };
  } else check(b.feedback === undefined);
  return r;
}
async function readJSON(request, limit = 48000) {
  check(/^application\/json(?:;|$)/i.test(request.headers.get('Content-Type') || ''));
  check(request.body);
  const reader = request.body.getReader(); const chunks = []; let size = 0;
  while (true) {
    const { done, value } = await reader.read(); if (done) break;
    size += value.length;
    if (size > limit) { await reader.cancel(); throw new Failure(413); }
    chunks.push(value);
  }
  const all = new Uint8Array(size); let offset = 0;
  for (const chunk of chunks) { all.set(chunk, offset); offset += chunk.length; }
  try { return JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(all)); }
  catch { throw new Failure(400); }
}
function response(data, status = 200) {
  return Response.json(data, { status, headers: { 'Cache-Control': 'no-store' } });
}
async function admin(request, env) {
  check(typeof env.READER_TOKEN === 'string' && env.READER_TOKEN.length >= 32, 503);
  const actual = request.headers.get('Authorization') || '';
  const digest = s => crypto.subtle.digest('SHA-256', new TextEncoder().encode(s));
  const [a, b] = await Promise.all([digest(actual), digest('Bearer ' + env.READER_TOKEN)]);
  const x = new Uint8Array(a), y = new Uint8Array(b);
  let different = 0; for (let i = 0; i < x.length; i++) different |= x[i] ^ y[i];
  check(different === 0, 401);
}
export default {
  async fetch(request, env) {
    try {
      const path = new URL(request.url).pathname;
      if (path === '/health' && request.method === 'GET') return response({ status: 'ok', schema: 1 });
      if (path === '/reports' && request.method === 'POST') {
        // The address is a transient limiter key only. Never persist it in D1/GitHub.
        check((await env.POST_LIMITER.limit({ key: request.headers.get('CF-Connecting-IP') || 'unknown' })).success, 429);
        const report = validate(await readJSON(request));
        const previous = await env.DB.prepare('SELECT id FROM reports WHERE id = ?').bind(report.id).first();
        if (previous) return response({ id: report.id, status: 'accepted' }, 202);
        const count = await env.DB.prepare("SELECT COUNT(*) AS n FROM reports WHERE received_at >= strftime('%Y-%m-%dT00:00:00Z', 'now')").first();
        check(count.n < 500, 429);
        await env.DB.prepare('INSERT OR IGNORE INTO reports (id, payload) VALUES (?, ?)')
          .bind(report.id, JSON.stringify(report)).run();
        return response({ id: report.id, status: 'accepted' }, 202);
      }
      if (path === '/admin/reports' && request.method === 'GET') {
        await admin(request, env);
        const rows = await env.DB.prepare('SELECT id, payload, received_at FROM reports WHERE delivered = 0 ORDER BY received_at, id LIMIT 20').all();
        return response({ reports: rows.results.map(r => ({ ...JSON.parse(r.payload), received_at: r.received_at })) });
      }
      if (path === '/admin/ack' && request.method === 'POST') {
        await admin(request, env); const body = await readJSON(request, 2048);
        exact(body, ['ids']); check(Array.isArray(body.ids) && body.ids.length <= 20);
        for (const id of body.ids) text(id, 36, UUID);
        if (body.ids.length) await env.DB.batch(body.ids.map(id => env.DB.prepare('UPDATE reports SET delivered = 1 WHERE id = ?').bind(id)));
        return response({ status: 'ok' });
      }
      return response({ error: 'Not found' }, 404);
    } catch (error) { return response({ error: 'Request rejected' }, error instanceof Failure ? error.status : 503); }
  },
  async scheduled(_event, env) {
    await env.DB.prepare("DELETE FROM reports WHERE received_at < strftime('%Y-%m-%dT%H:%M:%SZ', 'now', '-7 days')").run();
  }
};

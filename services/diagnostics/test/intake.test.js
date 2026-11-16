import { test } from 'node:test';
import assert from 'node:assert/strict';
import worker, { validate } from '../src/index.js';
const report = () => ({ schema: 1, id: '11111111-1111-4111-8111-111111111111',
  kind: 'startup-stalled', version: '1.9.8-lite.7', commit: 'abcdef1234', macos: '27.2.0',
  model: 'Mac15,13', chip: 'Apple M3', ram_gb: 16, stage: 'main', elapsed_s: 180 });
test('automatic reports have a strict allowlist; arbitrary strings cannot reach GitHub', () => {
  assert.deepEqual(validate(report()), report());
  for (const extra of [{ username: 'alice' }, { log: '/Users/alice/password' }, { feedback: {} }]) {
    assert.throws(() => validate({ ...report(), ...extra }));
  }
  for (const [key, value] of [['stage', '/Users/alice'], ['chip', 'computer-name'],
    ['model', 'alice@example.com'], ['elapsed_s', NaN], ['exit_code', -1], ['signal', 128]]) {
    assert.throws(() => validate({ ...report(), [key]: value }));
  }
});
test('manual text requires explicit manual kind and has bounded fields', () => {
  const b = { ...report(), kind: 'manual', feedback: { message: 'The window does not open.', email: '', launcher_log: '' } };
  assert.equal(validate(b).feedback.email, '');
  assert.throws(() => validate({ ...b, feedback: { ...b.feedback, screenshot: 'data' } }));
  assert.throws(() => validate({ ...b, feedback: { ...b.feedback, launcher_log: 'x'.repeat(24001) } }));
});
test('unauthorized readers cannot retrieve or acknowledge reports', async () => {
  for (const [path, method] of [['/admin/reports', 'GET'], ['/admin/ack', 'POST']]) {
    const result = await worker.fetch(new Request('https://example.test' + path, { method }), { READER_TOKEN: 'x'.repeat(64) });
    assert.equal(result.status, 401);
  }
});
test('oversized streaming bodies, unknown fields and rate limiting fail before persistence', async () => {
  let writes = 0;
  const env = { POST_LIMITER: { limit: async () => ({ success: true }) }, DB: { prepare: () => { writes++; throw Error('unexpected DB access'); } } };
  const post = body => new Request('https://example.test/reports', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body });
  assert.equal((await worker.fetch(post('x'.repeat(48001)), env)).status, 413);
  assert.equal((await worker.fetch(post(JSON.stringify({ ...report(), paths: ['/Users/alice'] })), env)).status, 400);
  assert.equal(writes, 0);
  env.POST_LIMITER.limit = async () => ({ success: false });
  assert.equal((await worker.fetch(post(JSON.stringify(report())), env)).status, 429);
});
test('intake is idempotent and IP is never included in stored payload', async () => {
  let stored; const queries = [];
  const env = { POST_LIMITER: { limit: async () => ({ success: true }) }, DB: {
    prepare(sql) { queries.push(sql); return { bind(...args) { this.args = args; return this; },
      async first() { return sql.startsWith('SELECT id') ? stored && { id: report().id } : { n: 0 }; },
      async run() { stored = this.args[1]; } }; }
  } };
  for (let i = 0; i < 2; i++) {
    const response = await worker.fetch(new Request('https://example.test/reports', { method: 'POST',
      headers: { 'Content-Type': 'application/json', 'CF-Connecting-IP': '192.0.2.7' }, body: JSON.stringify(report()) }), env);
    assert.equal(response.status, 202);
  }
  assert.equal(stored, JSON.stringify(report()));
  assert.equal(queries.filter(q => q.startsWith('INSERT')).length, 1);
});

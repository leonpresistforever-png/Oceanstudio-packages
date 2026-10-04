import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import { once } from 'node:events';
import { mkdtempSync, readFileSync, rmSync, statSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { randomBytes, createHash } from 'node:crypto';
import { createGateway } from '../packages/ocean-gateway/server.mjs';
import { PrivateStore } from '../packages/ocean-gateway/store.mjs';
import { open, read } from '../packages/ocean-gateway/transport.mjs';
import { parseRegistration } from '../packages/ocean-gateway/registrations.mjs';

test('native registration configuration is parsed with integrity and client binding', () => {
  const text = 'export const PUBLIC_CLIENT_ID = "fixture-client";\nexport const PUBLIC_CLIENT_SECRET = "fixture-registration-value";';
  const source = { sha256: createHash('sha256').update(text).digest('hex'), idSymbol: 'PUBLIC_CLIENT_ID', secretSymbol: 'PUBLIC_CLIENT_SECRET' };
  assert.equal(parseRegistration(text, source, 'fixture-client').clientSecret, 'fixture-registration-value');
  assert.throws(() => parseRegistration(text + 'changed', source, 'fixture-client'));
  assert.throws(() => parseRegistration(text, source, 'wrong-client'));
});

test('Ocean gateway forwards HTTP, scopes accounts, encrypts credentials and rejects OAuth replay', async t => {
  const directory = mkdtempSync(join(tmpdir(), 'ocean-gateway-test-'));
  const secret = randomBytes(32).toString('hex'), password = randomBytes(32).toString('hex');
  let tokenCalls = 0, refreshCalls = 0, onboardCalls = 0, generations = [], exchanges = [];
  const upstream = http.createServer(async (req, res) => {
    const chunks = []; for await (const c of req) chunks.push(c);
    const raw = Buffer.concat(chunks).toString();
    const url = new URL(req.url, 'http://localhost');
    res.setHeader('Content-Type', 'application/json');
    if (url.pathname === '/userinfo') return res.end('{"email":"fixture@example.test"}');
    if (url.pathname === '/v1internal:loadCodeAssist') return res.end('{"allowedTiers":[{"id":"free","isDefault":true}],"currentTier":{"name":"Fixture tier"}}');
    if (url.pathname === '/v1internal:onboardUser') {
      const body = JSON.parse(raw); assert.equal(body.tier_id, 'free'); onboardCalls++;
      return res.end(JSON.stringify(onboardCalls === 1 ? { done: false } : { done: true, response: { cloudaicompanionProject: { id: 'fixture-project' } } }));
    }
    if (url.pathname === '/v1internal:fetchAvailableModels') return res.end('{"models":{"fixture-gemini":{"displayName":"Fixture model"}}}');
    if (url.pathname === '/v1internal:retrieveUserQuota') return res.end('{"buckets":[{"modelId":"fixture-gemini","remainingFraction":0.75,"resetTime":"2026-10-05T00:00:00Z"}]}');
    if (url.pathname === '/v1internal:generateContent') {
      const body = JSON.parse(raw); generations.push(body);
      assert.equal(body.project, 'fixture-project'); assert.equal(body.userAgent, 'antigravity'); assert.equal(body.requestType, 'agent'); assert.ok(body.requestId);
      assert.equal(body.request.contents[0].role, 'user');
      return res.end('{"response":{"candidates":[{"content":{"parts":[{"text":"gemini-output"},{"functionCall":{"name":"lookup","args":{"id":1}}}]},"finishReason":"STOP"}],"usageMetadata":{"promptTokenCount":2,"candidatesTokenCount":3,"totalTokenCount":5}}}');
    }
    if (url.pathname.endsWith('/messages')) {
      assert.equal(req.headers['x-api-key'], 'anthropic-key'); assert.equal(req.headers['anthropic-version'], '2023-06-01');
      const body = JSON.parse(raw); generations.push(body);
      return res.end('{"content":[{"type":"text","text":"anthropic-output"},{"type":"tool_use","id":"call_real","name":"lookup","input":{"id":1}}],"usage":{"input_tokens":2,"output_tokens":3},"stop_reason":"tool_use"}');
    }
    if (url.pathname.endsWith('/models')) return res.end(JSON.stringify({ data: [{ id: 'fixture-model' }] }));
    if (url.pathname === '/token') {
      const form = new URLSearchParams(raw); exchanges.push(Object.fromEntries(form));
      if (form.get('grant_type') === 'refresh_token') refreshCalls++; else tokenCalls++;
      return res.end(JSON.stringify({ access_token: 'private-access-token', refresh_token: 'private-refresh-token', expires_in: 3600 }));
    }
    if (url.pathname === '/usage') return res.end(JSON.stringify({ plan_type: 'test-plan', rate_limit: { primary_window: { used_percent: 12 } } }));
    if (url.pathname.endsWith('/responses')) {
      const body = JSON.parse(raw); generations.push(body);
      assert.equal(body.store, false); assert.equal(body.stream, true); assert.equal(req.headers.authorization, 'Bearer private-access-token');
      res.setHeader('Content-Type', 'text/event-stream');
      res.end('data: ' + JSON.stringify({ type: 'response.completed', response: { output: [{ type: 'message', content: [{ type: 'output_text', text: 'responses-output' }] }], usage: { input_tokens: 3, output_tokens: 4, total_tokens: 7 } } }) + '\n\n'); return;
    }
    if (url.pathname.endsWith('/chat/completions')) {
      const body = JSON.parse(raw); generations.push(body);
      if (url.pathname.startsWith('/limited/')) { res.writeHead(429, { 'Retry-After': '1' }); return res.end('{"error":{"message":"limit"}}'); }
      if (body.stream) {
        res.setHeader('Content-Type', 'text/event-stream');
        const bytes = Buffer.from('data: ' + JSON.stringify({ choices: [{ delta: { content: 'real UTF-8: 🌊' }, finish_reason: null }] }) + '\r\n\r\ndata: [DONE]\r\n\r\n');
        for (const byte of bytes) res.write(Buffer.from([byte])); return res.end();
      }
      return res.end(JSON.stringify({ id: 'upstream-id', object: 'chat.completion', model: body.model, choices: [{ message: { role: 'assistant', content: 'forwarded-output' }, finish_reason: 'stop', index: 0 }], usage: { total_tokens: 7 } }));
    }
    res.writeHead(404); res.end('{}');
  });
  upstream.listen(0, '127.0.0.1'); await once(upstream, 'listening');
  const remote = 'http://127.0.0.1:' + upstream.address().port;
  const profiles = { codex: { clientId: 'native-test-client', authorization: remote + '/authorize', token: remote + '/token',
    baseUrl: remote + '/codex', quotaUrl: remote + '/usage', pkce: true, scope: 'openid offline_access' },
    antigravity: { clientId: 'google-fixture-client', clientSecret: 'native-fixture-registration', authorization: remote + '/authorize', token: remote + '/token',
      userInfo: remote + '/userinfo', baseUrl: remote, bootstrapUrl: remote, pkce: false, scope: 'fixture-scope' } };
  const gateway = createGateway({ directory, encryptionKey: secret, password, providerProfiles: profiles });
  gateway.server.listen(0, '127.0.0.1'); await once(gateway.server, 'listening');
  const base = 'http://127.0.0.1:' + gateway.server.address().port;
  t.after(() => { gateway.server.closeAllConnections(); gateway.server.close(); upstream.closeAllConnections(); upstream.close(); rmSync(directory, { recursive: true, force: true }); });
  async function call(path, { data, key, cookie, method, headers = {} } = {}) {
    const r = await fetch(base + path, { method: method ?? (data === undefined ? 'GET' : 'POST'), headers: { 'Content-Type': 'application/json', ...(cookie ? { Cookie: cookie } : {}), ...(key ? { Authorization: 'Bearer ' + key } : {}), ...headers }, body: data === undefined ? undefined : JSON.stringify(data) });
    const text = await r.text(); let body; try { body = JSON.parse(text); } catch { body = text; }
    return { status: r.status, headers: r.headers, body };
  }
  const login = await call('/api/auth/login', { data: { password } }); assert.equal(login.status, 200);
  const cookie = login.headers.get('set-cookie').split(';')[0];
  await t.test('management, inference and origin isolation', async () => {
    assert.equal((await call('/v1/models', { cookie })).status, 401);
    assert.equal((await call('/api/providers')).status, 401);
    assert.equal((await call('/api/providers', { cookie, headers: { Origin: 'https://hostile.example' } })).status, 403);
    const hostile = await open(base + '/health', { headers: { Host: 'hostile.example' } });
    await read(hostile); assert.equal(hostile.statusCode, 403);
  });
  let account, key;
  await t.test('real local model discovery and forwarding', async () => {
    const result = await call('/api/providers', { cookie, data: { provider: 'local', authType: 'local', baseUrl: remote + '/v1', format: 'openai' } });
    assert.equal(result.status, 201); account = result.body.connection;
    const issued = await call('/api/keys', { cookie, data: { allowedConnections: [account.id] } }); key = issued.body.key;
    const listed = await call('/v1/models', { key }); assert.equal(listed.body.data[0].id, 'local/fixture-model');
    const result2 = await call('/v1/chat/completions', { key, data: { model: 'local/fixture-model', messages: [{ role: 'user', content: 'question' }] } });
    assert.equal(result2.status, 200); assert.equal(result2.body.choices[0].message.content, 'forwarded-output');
    assert.equal(generations.at(-1).messages[0].content, 'question');
    assert.equal((await call('/v1/chat/completions', { key, data: { model: 'codex/fixture-model', messages: [{ role: 'user', content: 'q' }] } })).status, 403);
  });
  await t.test('SSE CRLF and fragmented multibyte UTF-8 survive forwarding', async () => {
    const result = await call('/v1/chat/completions', { key, data: { model: 'local/fixture-model', stream: true, messages: [{ role: 'user', content: 'q' }] } });
    assert.equal(result.status, 200); assert.match(result.body, /🌊/); assert.match(result.body, /\[DONE\]/);
  });
  await t.test('quota fallback uses a second permitted account', async () => {
    const result = await call('/api/providers', { cookie, data: { provider: 'limited', authType: 'local', baseUrl: remote + '/limited/v1' } });
    const limited = result.body.connection;
    const combo = await call('/api/combos', { cookie, data: { name: 'fallback', models: [{ connectionId: limited.id, model: 'limited/fixture-model' }, { connectionId: account.id, model: 'local/fixture-model' }] } });
    assert.equal(combo.status, 200);
    const issued = await call('/api/keys', { cookie, data: { allowedConnections: [limited.id, account.id] } });
    const done = await call('/v1/chat/completions', { key: issued.body.key, data: { model: 'fallback', messages: [{ role: 'user', content: 'q' }] } });
    assert.equal(done.status, 200); assert.equal(done.body.choices[0].message.content, 'forwarded-output');
  });
  let oauthAccount, oauthKey;
  await t.test('S256 exchange validates its original state, verifier and redirect and rejects replay', async () => {
    const redirect = 'http://localhost:1455/auth/callback';
    const r = await call('/api/oauth/codex/authorize?redirect_uri=' + encodeURIComponent(redirect), { cookie }); assert.equal(r.status, 200);
    const tx = r.body, auth = new URL(tx.authUrl);
    assert.equal(auth.searchParams.get('code_challenge_method'), 'S256');
    assert.equal(auth.searchParams.get('code_challenge'), createHash('sha256').update(tx.codeVerifier).digest('base64url'));
    const body = { state: tx.state, codeVerifier: tx.codeVerifier, redirectUri: redirect, code: 'one-use-code' };
    assert.equal((await call('/api/oauth/codex/exchange', { cookie, data: { ...body, codeVerifier: 'wrong' } })).status, 400);
    assert.equal(tokenCalls, 0);
    const exchange = await call('/api/oauth/codex/exchange', { cookie, data: body }); assert.equal(exchange.status, 200); oauthAccount = exchange.body.connection;
    assert.equal(exchanges[0].code_verifier, tx.codeVerifier); assert.equal(tokenCalls, 1);
    assert.equal((await call('/api/oauth/codex/exchange', { cookie, data: body })).status, 400); assert.equal(tokenCalls, 1);
    oauthKey = (await call('/api/keys', { cookie, data: { allowedConnections: [oauthAccount.id] } })).body.key;
  });
  await t.test('Codex wire conversion and live upstream quota response', async () => {
    const result = await call('/v1/chat/completions', { key: oauthKey, data: { model: 'codex/fixture-model', messages: [{ role: 'system', content: 'instructions' }, { role: 'user', content: 'question' }] } });
    assert.equal(result.status, 200); assert.equal(result.body.choices[0].message.content, 'responses-output'); assert.equal(generations.at(-1).instructions, 'instructions');
    const quota = await call('/api/usage/' + oauthAccount.id, { cookie }); assert.equal(quota.body.planName, 'test-plan'); assert.equal(quota.body.raw.rate_limit.primary_window.used_percent, 12);
  });
  await t.test('refresh uses the issuing client and coalesces concurrent requests', async () => {
    const stored = gateway.store.account(oauthAccount.id); stored.tokens.expiresAt = Date.now() - 1;
    gateway.adapters.profiles.codex.clientId = 'changed-global-client';
    await Promise.all([gateway.adapters.credential(stored), gateway.adapters.credential(stored)]);
    assert.equal(refreshCalls, 1); assert.equal(exchanges.at(-1).client_id, 'native-test-client');
  });
  await t.test('Google native grant, project provisioning, tool translation and quota fields', async () => {
    const redirect = 'http://127.0.0.1:45555/callback';
    const tx = (await call('/api/oauth/antigravity/authorize?redirect_uri=' + encodeURIComponent(redirect), { cookie })).body;
    assert.equal(tx.flowType, 'authorization_code'); assert.equal(new URL(tx.authUrl).searchParams.has('code_challenge'), false);
    const exchange = await call('/api/oauth/antigravity/exchange', { cookie, data: { state: tx.state, codeVerifier: tx.codeVerifier, redirectUri: redirect, code: 'google-code' } });
    assert.equal(exchange.status, 200); assert.equal(onboardCalls, 2); assert.equal(exchanges.at(-1).code_verifier, undefined);
    const account = exchange.body.connection;
    const key = (await call('/api/keys', { cookie, data: { allowedConnections: [account.id] } })).body.key;
    const out = await call('/v1/chat/completions', { key, data: { model: 'antigravity/fixture-gemini', messages: [{ role: 'user', content: 'q' }] } });
    assert.equal(out.status, 200); assert.equal(out.body.choices[0].message.content, 'gemini-output');
    assert.equal(out.body.choices[0].message.tool_calls[0].function.arguments, '{"id":1}');
    const quota = (await call('/api/usage/' + account.id, { cookie })).body;
    assert.equal(quota.quotas['fixture-gemini'].remainingPercentage, 75); assert.equal(quota.source, 'provider');
  });
  await t.test('Anthropic message and tool-call conversion follows its wire contract', async () => {
    const account = (await call('/api/providers', { cookie, data: { provider: 'claude', authType: 'local', format: 'anthropic', baseUrl: remote + '/v1', apiKey: 'anthropic-key' } })).body.connection;
    const key = (await call('/api/keys', { cookie, data: { allowedConnections: [account.id] } })).body.key;
    const out = await call('/v1/chat/completions', { key, data: { model: 'claude/fixture-model', messages: [{ role: 'system', content: 'instructions' }, { role: 'user', content: 'q' }] } });
    assert.equal(out.status, 200); assert.equal(out.body.choices[0].finish_reason, 'tool_calls'); assert.equal(out.body.choices[0].message.content, 'anthropic-output');
    assert.equal(generations.at(-1).system, 'instructions');
  });
  await t.test('encrypted state survives restart without plaintext credentials', async () => {
    const path = join(directory, 'ocean-state.aesgcm'), saved = readFileSync(path, 'utf8');
    assert.ok(!saved.includes('private-access-token')); assert.ok(!saved.includes(oauthKey)); assert.equal(statSync(path).mode & 0o777, 0o600);
    assert.equal(new PrivateStore(directory, secret).account(oauthAccount.id).tokens.access_token, 'private-access-token');
    assert.throws(() => new PrivateStore(directory, randomBytes(32).toString('hex')));
  });
  await t.test('deleting an account revokes old inference access', async () => {
    assert.equal((await call('/api/providers/' + account.id, { cookie, method: 'DELETE' })).status, 200);
    assert.equal((await call('/v1/models', { key })).body.data.length, 0);
    assert.equal((await call('/v1/chat/completions', { key, data: { model: 'local/fixture-model', messages: [{ role: 'user', content: 'q' }] } })).status, 403);
  });
});

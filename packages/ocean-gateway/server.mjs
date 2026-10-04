import http from 'node:http';
import { randomBytes, randomUUID } from 'node:crypto';
import { once } from 'node:events';
import { pathToFileURL } from 'node:url';
import { join } from 'node:path';
import { PrivateStore, equal } from './store.mjs';
import { Providers, profiles } from './providers.mjs';
import { Authorization } from './oauth.mjs';
import { safeEndpoint, read, UpstreamError } from './transport.mjs';

export const VERSION = '1.0.0';
const allowedFormats = ['openai', 'gemini', 'anthropic'];
const idOk = value => typeof value === 'string' && /^[A-Za-z0-9_-]{1,100}$/.test(value);

export function createGateway({ directory, encryptionKey, password, providerProfiles = profiles }) {
  const store = new PrivateStore(directory, encryptionKey), adapters = new Providers(store, providerProfiles), authorization = new Authorization(store, adapters);
  if (!password || password.length < 24) throw Error('A generated private management password is required');
  const sessions = new Map(), cooldowns = new Map(); let loginAttempts = 0, windowStart = Date.now();
  function send(res, status, body, headers = {}) {
    res.writeHead(status, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff', ...headers });
    res.end(JSON.stringify(body));
  }
  async function body(req) {
    if (!(req.headers['content-type'] ?? '').startsWith('application/json')) throw new UpstreamError(415, 'JSON Content-Type is required');
    const text = await read(req, 2 * 1024 * 1024);
    let value; try { value = JSON.parse(text); } catch { throw new UpstreamError(400, 'Invalid JSON request'); }
    if (!value || typeof value !== 'object' || Array.isArray(value)) throw new UpstreamError(400, 'A JSON object is required');
    return value;
  }
  function manage(req) {
    const cookie = /(?:^|;\s*)auth_token=([A-Za-z0-9_-]+)/.exec(req.headers.cookie ?? '')?.[1];
    const expiry = sessions.get(cookie);
    if (!expiry || expiry < Date.now()) { sessions.delete(cookie); throw new UpstreamError(401, 'A management session is required'); }
  }
  function inference(req) {
    const token = /^Bearer (ocean_[A-Za-z0-9_-]+)$/.exec(req.headers.authorization ?? '')?.[1];
    const key = token && store.inferenceKey(token);
    if (!key) throw new UpstreamError(401, 'An account-scoped Ocean inference key is required');
    return key;
  }
  function routes(model, key) {
    const combo = store.state.combos.find(c => c.name === model);
    const wanted = combo ? combo.models : [{ model }]; const result = [];
    for (const item of wanted) {
      const slash = item.model.indexOf('/'), provider = slash < 0 ? null : item.model.slice(0, slash), bare = slash < 0 ? item.model : item.model.slice(slash + 1);
      for (const id of key.allowedConnections) {
        const a = store.account(id);
        if (!a || (item.connectionId && id !== item.connectionId) || (provider && a.provider !== provider)) continue;
        if (!item.connectionId && !provider && !a.models?.some(m => m.id === bare)) continue;
        result.push({ account: a, model: bare });
      }
    }
    if (!result.length) throw new UpstreamError(403, 'This key has no connected account for that model');
    return result;
  }
  async function complete(req, res, request, key) {
    if (typeof request.model !== 'string' || !Array.isArray(request.messages) || !request.messages.length) throw new UpstreamError(400, 'model and nonempty messages are required');
    if (request.messages.some(m => !m || !['system', 'developer', 'user', 'assistant', 'tool'].includes(m.role)
      || (m.content != null && typeof m.content !== 'string' && !Array.isArray(m.content)))) throw new UpstreamError(400, 'Invalid message role or content');
    if (request.tools && (!Array.isArray(request.tools) || request.tools.some(t => t.type !== 'function' || typeof t.function?.name !== 'string'))) throw new UpstreamError(400, 'Invalid function tools');
    const controller = new AbortController(); res.on('close', () => { if (!res.writableEnded) controller.abort(); });
    let last;
    for (const route of routes(request.model, key)) {
      const cooldown = cooldowns.get(route.account.id) ?? 0;
      if (cooldown > Date.now()) { last = new UpstreamError(429, 'Account is cooling down after a provider limit'); continue; }
      try {
        const { format, response } = await adapters.request(route.account, route.model, request, controller.signal);
        if (response.statusCode < 200 || response.statusCode >= 300) {
          const code = response.statusCode; await read(response, 1024 * 1024);
          if (code === 429) cooldowns.set(route.account.id, Date.now() + Math.min(300000, Math.max(1000, Number(response.headers['retry-after'] ?? 10) * 1000)));
          throw new UpstreamError(code, `Provider ${route.account.provider} returned HTTP ${code}`, response.headers['retry-after']);
        }
        route.account.lastUsedAt = Date.now(); store.save();
        if (request.stream === true) {
          res.writeHead(200, { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no' });
          try {
            for await (const event of adapters.stream(format, response, request.model)) {
              if (!res.write('data: ' + JSON.stringify(event) + '\n\n')) await once(res, 'drain', { signal: controller.signal });
            }
            res.end('data: [DONE]\n\n');
          } catch (error) {
            // Never retry after forwarding deltas: a second generation would duplicate output/tools.
            if (!res.destroyed) res.end('data: ' + JSON.stringify({ error: { message: error.message, type: 'upstream_error' } }) + '\n\ndata: [DONE]\n\n');
          }
        } else send(res, 200, await adapters.collect(format, response, request.model));
        return;
      } catch (error) {
        if (res.headersSent || controller.signal.aborted) throw error;
        last = error;
        if (error.status && ![401, 403, 408, 429].includes(error.status) && error.status < 500) throw error;
      }
    }
    throw last ?? new UpstreamError(503, 'No connected account is ready');
  }
  const server = http.createServer(async (req, res) => {
    try {
      // Reject external Host/Origin values to resist DNS rebinding and browser CSRF.
      const host = new URL('http://' + (req.headers.host ?? ''));
      if (!['localhost', '127.0.0.1', '[::1]'].includes(host.hostname)) throw new UpstreamError(403, 'Loopback Host is required');
      if (req.headers.origin && req.headers.origin !== host.origin) throw new UpstreamError(403, 'Cross-origin management requests are rejected');
      const url = new URL(req.url, host), path = url.pathname;
      if (req.method === 'GET' && ['/health', '/api/monitoring/health'].includes(path)) return send(res, 200, { status: 'ok', engine: 'ocean', version: VERSION });
      if (req.method === 'POST' && path === '/api/auth/login') {
        if (Date.now() - windowStart > 60000) { loginAttempts = 0; windowStart = Date.now(); }
        if (++loginAttempts > 30) throw new UpstreamError(429, 'Management login rate limit reached');
        const value = await body(req);
        if (!equal(value.password, password)) throw new UpstreamError(401, 'Management authentication failed');
        for (const [session, expiry] of sessions) if (expiry < Date.now()) sessions.delete(session);
        const token = randomBytes(32).toString('base64url'); sessions.set(token, Date.now() + 24 * 60 * 60 * 1000);
        return send(res, 200, { success: true }, { 'Set-Cookie': `auth_token=${token}; HttpOnly; SameSite=Strict; Path=/api/; Max-Age=86400` });
      }
      if (path.startsWith('/v1/')) {
        const key = inference(req);
        if (req.method === 'GET' && path === '/v1/models') {
          const data = [];
          for (const id of key.allowedConnections) {
            const a = store.account(id); if (!a) continue;
            const models = a.models ?? await adapters.models(a);
            for (const model of models) data.push({ ...model, id: `${a.provider}/${model.id}`, object: 'model', owned_by: a.provider });
          }
          return send(res, 200, { object: 'list', data: [...new Map(data.map(m => [m.id, m])).values()] });
        }
        if (req.method === 'POST' && path === '/v1/chat/completions') return await complete(req, res, await body(req), key);
        throw new UpstreamError(404, 'Unknown inference route');
      }
      manage(req);
      if (req.method === 'GET' && path === '/api/providers') return send(res, 200, { connections: store.state.accounts.filter(a => !url.searchParams.has('provider') || a.provider === url.searchParams.get('provider')).map(a => store.publicAccount(a)) });
      if (req.method === 'POST' && path === '/api/providers') {
        const value = await body(req);
        if (!idOk(value.provider) || !allowedFormats.includes(value.format ?? 'openai')) throw new UpstreamError(400, 'Invalid provider ID or format');
        safeEndpoint(value.baseUrl, value.authType === 'local');
        if (value.authType !== 'local' && (typeof value.apiKey !== 'string' || !value.apiKey)) throw new UpstreamError(400, 'Provider credential is required');
        const account = { id: randomBytes(16).toString('hex'), provider: value.provider, displayName: value.displayName ?? value.provider,
          authType: value.authType === 'local' ? 'local' : 'api_key', baseUrl: value.baseUrl, format: value.format ?? 'openai', apiKey: value.apiKey ?? '', createdAt: Date.now(), isActive: true };
        await adapters.models(account); store.state.accounts.push(account); store.save();
        return send(res, 201, { connection: store.publicAccount(account) });
      }
      let match = /^\/api\/oauth\/([A-Za-z0-9_-]+)\/(authorize|exchange)$/.exec(path);
      if (match?.[2] === 'authorize' && req.method === 'GET') return send(res, 200, await authorization.begin(match[1], url.searchParams.get('redirect_uri')));
      if (match?.[2] === 'exchange' && req.method === 'POST') return send(res, 200, await authorization.exchange(match[1], await body(req)));
      if (req.method === 'POST' && path === '/api/keys') { const value = await body(req); return send(res, 201, { key: store.issueKey(value.allowedConnections, value.name) }); }
      match = /^\/api\/providers\/([A-Za-z0-9_-]+)(\/models)?$/.exec(path);
      if (match) {
        const account = store.account(match[1]); if (!account) throw new UpstreamError(404, 'Account not found');
        if (req.method === 'GET' && match[2]) return send(res, 200, { models: await adapters.models(account), source: 'provider' });
        if (req.method === 'DELETE' && !match[2]) {
          store.state.accounts = store.state.accounts.filter(a => a.id !== account.id);
          for (const k of store.state.keys) k.allowedConnections = k.allowedConnections.filter(id => id !== account.id);
          store.save(); return send(res, 200, { success: true });
        }
      }
      match = /^\/api\/usage\/([A-Za-z0-9_-]+)$/.exec(path);
      if (req.method === 'GET' && match) {
        const account = store.account(match[1]); if (!account) throw new UpstreamError(404, 'Account not found');
        return send(res, 200, await adapters.quota(account));
      }
      if (req.method === 'GET' && path === '/api/combos') return send(res, 200, { combos: store.state.combos });
      if ((req.method === 'POST' && path === '/api/combos') || (req.method === 'PUT' && path.startsWith('/api/combos/'))) {
        const value = await body(req);
        if (!idOk(value.name) || !Array.isArray(value.models) || !value.models.length || value.models.length > 32
          || value.models.some(m => !store.account(m.connectionId) || typeof m.model !== 'string')) throw new UpstreamError(400, 'Fallback must contain connected accounts and model IDs');
        const old = req.method === 'PUT' ? store.state.combos.find(c => c.id === path.split('/').at(-1)) : null;
        if (req.method === 'PUT' && !old) throw new UpstreamError(404, 'Fallback not found');
        const combo = { id: old?.id ?? randomUUID(), name: value.name, displayName: value.displayName, strategy: 'priority', models: value.models };
        store.state.combos = store.state.combos.filter(c => c.id !== combo.id); store.state.combos.push(combo); store.save();
        return send(res, 200, combo);
      }
      throw new UpstreamError(404, 'Unknown management route');
    } catch (error) {
      if (res.headersSent) { res.destroy(); return; }
      const status = error.status ?? (error instanceof TypeError ? 400 : 500);
      send(res, status, { error: { message: error.message, type: status >= 500 ? 'gateway_error' : 'invalid_request_error' } },
        error.retryAfter ? { 'Retry-After': error.retryAfter } : {});
    }
  });
  server.requestTimeout = 240000; server.headersTimeout = 15000;
  return { server, store, authorization, adapters };
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const directory = process.env.OCEAN_GATEWAY_DATA ?? process.env.DATA_DIR ?? join(process.env.PREFIX ?? '/data/data/studio.ocean.app/files/usr', 'var/lib/ocean-gateway');
  const { server } = createGateway({ directory, encryptionKey: process.env.STORAGE_ENCRYPTION_KEY, password: process.env.INITIAL_PASSWORD });
  const port = Number(process.env.OCEAN_GATEWAY_PORT ?? 20129);
  if (!Number.isInteger(port) || port < 1 || port > 65535) throw Error('Invalid gateway port');
  server.listen(port, '127.0.0.1', () => console.log(`Ocean Gateway ${VERSION} ready at http://127.0.0.1:${port}/v1`));
  const shutdown = () => { server.close(); server.closeAllConnections(); };
  process.on('SIGTERM', shutdown); process.on('SIGINT', shutdown);
}

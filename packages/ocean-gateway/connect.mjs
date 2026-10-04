import http from 'node:http';
import { readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { spawn } from 'node:child_process';
import { json, open, read } from './transport.mjs';
import { equal } from './store.mjs';

const origin = 'http://127.0.0.1:' + (process.env.OCEAN_GATEWAY_PORT ?? 20129);
const directory = process.env.OCEAN_GATEWAY_DATA;
const action = process.argv[2];
async function healthy() {
  const result = await json(origin + '/health', { timeout: 2000 });
  if (result.engine !== 'ocean') throw Error('This port belongs to a different server');
  return result;
}
async function management() {
  const env = readFileSync(join(directory, '.env'), 'utf8');
  const password = /^INITIAL_PASSWORD=(.+)$/m.exec(env)?.[1];
  const response = await open(origin + '/api/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: { password } });
  await read(response);
  const cookie = response.headers['set-cookie']?.[0]?.split(';')[0];
  if (response.statusCode !== 200 || !cookie) throw Error('Private management authentication failed');
  return async (path, body) => json(origin + path, { method: body === undefined ? 'GET' : 'POST',
    headers: { Cookie: cookie, 'Content-Type': 'application/json' }, body });
}
async function saveInference(call, account) {
  const result = await call('/api/keys', { name: 'Ocean terminal', allowedConnections: [account.id] });
  const config = { baseUrl: origin + '/v1', apiKey: result.key, account: account.id };
  const file = join(directory, 'terminal-client.json'); writeFileSync(file, JSON.stringify(config, null, 2) + '\n', { mode: 0o600 });
  console.log('Connected ' + account.displayName + '; private client configuration: ' + file);
}
if (action === 'wait') {
  let error;
  for (let i = 0; i < 60; i++) {
    try { await healthy(); console.log('Ocean Gateway is ready at ' + origin + '/v1'); process.exit(0); }
    catch (e) { error = e; await new Promise(r => setTimeout(r, 500)); }
  }
  throw error;
} else if (action === 'status') console.log(JSON.stringify(await healthy()));
else if (action === 'add-local') {
  const call = await management();
  const added = await call('/api/providers', { provider: 'local', authType: 'local', format: 'openai',
    baseUrl: process.argv[3] ?? 'http://127.0.0.1:11434/v1', displayName: 'Local inference' });
  await saveInference(call, added.connection);
} else if (action === 'connect') {
  const provider = process.argv[3];
  if (!['codex', 'antigravity', 'gemini-cli'].includes(provider)) throw Error('Select a known browser authorization adapter');
  const call = await management(); let tx; let completed = false;
  const receiver = http.createServer(async (req, res) => {
    try {
      const callback = new URL(req.url, 'http://127.0.0.1');
      if (req.method !== 'GET' || completed || callback.searchParams.getAll('state').length !== 1
        || callback.searchParams.getAll('code').length > 1 || callback.pathname !== (provider === 'codex' ? '/auth/callback' : '/callback') || !equal(callback.searchParams.get('state'), tx?.state)) {
        res.writeHead(400); res.end('Invalid authorization callback'); return;
      }
      completed = true;
      if (callback.searchParams.has('error')) throw Error('Provider authorization was declined');
      const account = await call('/api/oauth/' + provider + '/exchange', { state: tx.state, codeVerifier: tx.codeVerifier,
        redirectUri: tx.redirectUri, code: callback.searchParams.get('code') });
      await saveInference(call, account.connection);
      res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store', 'Content-Security-Policy': "default-src 'none'; style-src 'unsafe-inline'" });
      res.end('<!doctype html><title>Ocean connected</title><p>Your account is connected. Return to Ocean Studio.</p>'); receiver.close();
    } catch (e) { res.writeHead(502); res.end('Authorization did not complete. See the Ocean terminal.'); console.error(e.message); receiver.close(); process.exitCode = 1; }
  });
  await new Promise((resolve, reject) => { receiver.once('error', reject); receiver.listen(provider === 'codex' ? 1455 : 0, '127.0.0.1', resolve); });
  const host = provider === 'codex' ? 'localhost' : '127.0.0.1';
  const redirect = `http://${host}:${receiver.address().port}/${provider === 'codex' ? 'auth/callback' : 'callback'}`;
  try {
    tx = await call('/api/oauth/' + provider + '/authorize?redirect_uri=' + encodeURIComponent(redirect));
    const browser = process.platform === 'android' ? '/system/bin/am' : 'xdg-open';
    const args = process.platform === 'android' ? ['start', '-a', 'android.intent.action.VIEW', '-d', tx.authUrl] : [tx.authUrl];
    const launch = spawn(browser, args, { stdio: 'ignore' });
    launch.once('error', () => { console.error('The system browser could not open. No callback URL or credential has been printed.'); receiver.close(); process.exitCode = 1; });
    launch.once('exit', code => { if (code) { receiver.close(); process.exitCode = 1; } });
    console.log('Waiting for authorization in your browser…');
    const timer = setTimeout(() => { console.error('Authorization expired'); receiver.closeAllConnections(); receiver.close(); process.exitCode = 1; }, 600000);
    receiver.once('close', () => clearTimeout(timer));
  } catch (error) { receiver.close(); throw error; }
} else throw Error('Unknown gateway client action');

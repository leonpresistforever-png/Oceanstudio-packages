import { randomBytes, createHash } from 'node:crypto';
import { json, UpstreamError } from './transport.mjs';
import { equal } from './store.mjs';
import { registration } from './registrations.mjs';

export class Authorization {
  constructor(store, providers) { this.store = store; this.providers = providers; this.pending = new Map(); }
  async begin(provider, redirectUri) {
    let profile = this.providers.profiles[provider];
    if (!profile) throw new UpstreamError(400, 'Unknown account authorization adapter');
    profile = await registration(profile, this.store);
    const redirect = new URL(redirectUri);
    if (redirect.protocol !== 'http:' || !['localhost', '127.0.0.1'].includes(redirect.hostname)
      || redirect.username || redirect.password || redirect.search || redirect.hash || !redirect.port
      || !['/callback', '/auth/callback'].includes(redirect.pathname)) throw new UpstreamError(400, 'Authorization requires its bound loopback callback');
    if (provider === 'codex' && redirect.href !== 'http://localhost:1455/auth/callback') throw new UpstreamError(400, 'The Codex native client requires localhost:1455/auth/callback');
    const now = Date.now();
    for (const [key, value] of this.pending) if (value.expiresAt < now) this.pending.delete(key);
    if (this.pending.size >= 16) throw new UpstreamError(429, 'Too many pending authorizations');
    const state = randomBytes(32).toString('base64url'), verifier = randomBytes(48).toString('base64url');
    const url = new URL(profile.authorization);
    const parameters = { response_type: 'code', client_id: profile.clientId, redirect_uri: redirect.href, scope: profile.scope, state };
    if (profile.pkce) {
      parameters.code_challenge = createHash('sha256').update(verifier).digest('base64url'); parameters.code_challenge_method = 'S256';
    }
    if (provider === 'codex') Object.assign(parameters, { id_token_add_organizations: 'true', codex_cli_simplified_flow: 'true', originator: 'codex_cli_rs', prompt: 'login' });
    if (['antigravity', 'gemini-cli'].includes(provider)) Object.assign(parameters, { access_type: 'offline', prompt: 'consent' });
    for (const [name, value] of Object.entries(parameters)) url.searchParams.set(name, value);
    this.pending.set(state, { provider, verifier, redirect: redirect.href, expiresAt: now + 600000, profile });
    return { authUrl: url.href, state, codeVerifier: verifier, redirectUri: redirect.href,
      flowType: profile.pkce ? 'authorization_code_pkce' : 'authorization_code' };
  }
  async exchange(provider, body) {
    const tx = this.pending.get(body.state);
    if (!tx || tx.expiresAt < Date.now() || tx.provider !== provider || !equal(body.codeVerifier, tx.verifier)
      || body.redirectUri !== tx.redirect || typeof body.code !== 'string' || !body.code || body.code.length > 8192) {
      throw new UpstreamError(400, 'Authorization transaction did not match its one-use callback');
    }
    // Consume BEFORE sending the provider a code, preventing concurrent replay.
    this.pending.delete(body.state);
    const form = new URLSearchParams({ grant_type: 'authorization_code', client_id: tx.profile.clientId,
      code: body.code, redirect_uri: tx.redirect });
    if (tx.profile.pkce) form.set('code_verifier', tx.verifier);
    if (tx.profile.clientSecret) form.set('client_secret', tx.profile.clientSecret);
    const tokens = await json(tx.profile.token, { method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, body: form.toString() });
    if (!tokens.access_token) throw new UpstreamError(502, 'Provider did not return an access token');
    tokens.expiresAt = Date.now() + Number(tokens.expires_in ?? 3600) * 1000;
    let email = '', accountId = '';
    if (provider === 'codex' && tokens.id_token) {
      // Used only as display/routing hints AFTER a HTTPS code exchange, never as signature-based authorization.
      const claims = JSON.parse(Buffer.from(tokens.id_token.split('.')[1], 'base64url').toString());
      email = claims.email ?? ''; accountId = claims['https://api.openai.com/auth']?.chatgpt_account_id ?? '';
    } else if (tx.profile.userInfo) {
      const info = await json(tx.profile.userInfo, { headers: { Authorization: `Bearer ${tokens.access_token}` } }); email = info.email ?? '';
    }
    const account = { id: randomBytes(16).toString('hex'), provider, authType: 'oauth', isActive: true, email,
      displayName: email || provider, accountId, baseUrl: tx.profile.baseUrl, tokens,
      oauthClient: { clientId: tx.profile.clientId, clientSecret: tx.profile.clientSecret, token: tx.profile.token }, createdAt: Date.now() };
    await this.providers.bootstrap(account);
    await this.providers.models(account);
    const existing = this.store.state.accounts.find(a => a.provider === provider && (accountId ? a.accountId === accountId : email && a.email === email));
    if (existing) account.id = existing.id;
    this.store.state.accounts = this.store.state.accounts.filter(a => a.id !== account.id);
    this.store.state.accounts.push(account); this.store.save();
    return { success: true, connection: this.store.publicAccount(account) };
  }
}

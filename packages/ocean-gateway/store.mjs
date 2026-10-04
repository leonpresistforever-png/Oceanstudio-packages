// Ocean-authored private state store. No gateway framework dependency.
import { mkdirSync, readFileSync, writeFileSync, renameSync, existsSync, chmodSync } from 'node:fs';
import { join } from 'node:path';
import { randomBytes, createCipheriv, createDecipheriv, createHash, timingSafeEqual } from 'node:crypto';

export const digest = value => createHash('sha256').update(value).digest('hex');
export const equal = (a, b) => {
  const x = Buffer.from(String(a ?? '')), y = Buffer.from(String(b ?? ''));
  return x.length === y.length && timingSafeEqual(x, y);
};
export class PrivateStore {
  constructor(directory, secret) {
    mkdirSync(directory, { recursive: true, mode: 0o700 });
    chmodSync(directory, 0o700);
    this.file = join(directory, 'ocean-state.aesgcm');
    if (!/^[a-f0-9]{64}$/i.test(secret ?? '')) throw Error('A private 256-bit storage key is required');
    this.secret = Buffer.from(secret, 'hex');
    this.state = { accounts: [], keys: [], combos: [], registrations: {} };
    if (existsSync(this.file)) {
      const envelope = JSON.parse(readFileSync(this.file, 'utf8'));
      if (envelope.version !== 1) throw Error('Unknown Ocean state version; preserving the file');
      const decipher = createDecipheriv('aes-256-gcm', this.secret, Buffer.from(envelope.nonce, 'base64'));
      decipher.setAAD(Buffer.from('OceanGatewayState/1'));
      decipher.setAuthTag(Buffer.from(envelope.tag, 'base64'));
      this.state = JSON.parse(Buffer.concat([decipher.update(Buffer.from(envelope.body, 'base64')), decipher.final()]).toString());
      for (const name of ['accounts', 'keys', 'combos']) if (!Array.isArray(this.state[name])) throw Error('Invalid private state');
      this.state.registrations ??= {};
    }
  }
  save() {
    const nonce = randomBytes(12), cipher = createCipheriv('aes-256-gcm', this.secret, nonce);
    cipher.setAAD(Buffer.from('OceanGatewayState/1'));
    const body = Buffer.concat([cipher.update(JSON.stringify(this.state)), cipher.final()]);
    const temporary = this.file + '.' + randomBytes(8).toString('hex') + '.new';
    writeFileSync(temporary, JSON.stringify({ version: 1, nonce: nonce.toString('base64'), tag: cipher.getAuthTag().toString('base64'), body: body.toString('base64') }), { flag: 'wx', mode: 0o600 });
    renameSync(temporary, this.file);
  }
  account(id) { return this.state.accounts.find(a => a.id === id && a.isActive !== false); }
  publicAccount(a) {
    return { id: a.id, provider: a.provider, displayName: a.displayName, email: a.email, isActive: a.isActive !== false,
      authType: a.authType, createdAt: a.createdAt, lastUsedAt: a.lastUsedAt ?? null };
  }
  issueKey(connections, name = 'Ocean') {
    if (!Array.isArray(connections) || !connections.length || connections.some(id => !this.account(id))) throw Error('Inference keys need existing account IDs');
    const key = 'ocean_' + randomBytes(32).toString('base64url');
    const record = { id: randomBytes(16).toString('hex'), hash: digest(key), name, allowedConnections: [...new Set(connections)] };
    this.state.keys.push(record); this.save(); return key;
  }
  inferenceKey(value) { const hash = digest(value); return this.state.keys.find(k => equal(k.hash, hash)); }
}

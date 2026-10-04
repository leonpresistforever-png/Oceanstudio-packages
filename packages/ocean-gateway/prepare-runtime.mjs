import { mkdirSync, readFileSync, writeFileSync, existsSync, chmodSync, appendFileSync } from 'node:fs';
import { join } from 'node:path';
import { randomBytes } from 'node:crypto';

const directory = process.argv[2];
if (!directory) throw Error('Ocean gateway data directory is required');
mkdirSync(directory, { recursive: true, mode: 0o700 }); chmodSync(directory, 0o700);
const file = join(directory, '.env');
if (!existsSync(file)) writeFileSync(file, '', { flag: 'wx', mode: 0o600 });
let text = readFileSync(file, 'utf8');
for (const name of ['INITIAL_PASSWORD', 'STORAGE_ENCRYPTION_KEY']) {
  const pattern = name === 'STORAGE_ENCRYPTION_KEY' ? '=[a-fA-F0-9]{64}$' : '=[a-zA-Z0-9_-]{24,}$';
  if (!new RegExp('^' + name + pattern, 'm').test(text)) {
    if (new RegExp('^' + name + '=', 'm').test(text)) throw Error('Preserving existing invalid ' + name + '; inspect the private environment file');
    const entry = name + '=' + randomBytes(32).toString('hex') + '\n'; appendFileSync(file, entry); text += entry;
  }
}
chmodSync(file, 0o600);
console.log('Ocean gateway private state is initialized');

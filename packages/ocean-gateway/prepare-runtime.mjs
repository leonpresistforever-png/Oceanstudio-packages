// Ocean's private Node runtime preparation, using official npm dependencies only.
// Account routes import Playwright even when authorization uses an external browser.
import { mkdirSync, readFileSync, writeFileSync, renameSync, existsSync } from 'node:fs';
import { join } from 'node:path';
import { homedir } from 'node:os';

export function prepareRuntime(root, cache = process.env.XDG_CACHE_HOME || join(homedir(), '.cache')) {
  mkdirSync(cache, { recursive: true, mode: 0o700 });
  const targets = [
    join(root, 'node_modules/playwright-core/lib/coreBundle.js'),
    join(root, 'node_modules/omniroute/dist/node_modules/playwright-core/lib/coreBundle.js'),
  ].filter(existsSync);
  if (!targets.length) throw new Error('The gateway Playwright dependency is missing');
  const marker = '/* Ocean Android cache directory */';
  for (const file of targets) {
    let source = readFileSync(file, 'utf8');
    if (source.includes(marker)) continue;
    for (const name of ['defaultCacheDirectory', 'defaultCacheDirectory2', 'baseDaemonDir']) {
      const pattern = new RegExp(`(${name} = \\(\\(\\) => \\{)([\\s\\S]*?)(\\}\\)\\(\\);)`, 'g');
      let matches = 0;
      source = source.replace(pattern, (all, start, body, end) => {
        matches++;
        const directory = 'process.env.XDG_CACHE_HOME || require("node:path").join(require("node:os").homedir(), ".cache")';
        const result = name === 'baseDaemonDir' ? `require("node:path").join(${directory}, "ms-playwright", "daemon")` : directory;
        return `${start}\n      ${marker}\n      if (process.platform === "android") return ${result};${body}${end}`;
      });
      if (matches !== 1) throw new Error(`Unexpected Playwright cache layout: ${name} (${matches})`);
    }
    // Change only these cache-directory computations, never OAuth or browser behavior.
    const temporary = file + '.ocean-new';
    writeFileSync(temporary, source);
    renameSync(temporary, file);
  }
}

if (process.argv[1]?.endsWith('prepare-runtime.mjs')) prepareRuntime(process.argv[2]);

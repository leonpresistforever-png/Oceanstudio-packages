// Native OAuth registration configuration is retrieved separately from code.
// Only two scalar constants are parsed; downloaded source is never evaluated.
import { createHash } from 'node:crypto';
import { open, read, UpstreamError } from './transport.mjs';

export const registrationSources = Object.freeze({
  antigravity: {
    url: 'https://raw.githubusercontent.com/NoeFabris/opencode-antigravity-auth/16e0056431d0a1291ee66e5938c732720b13a851/src/constants.ts',
    sha256: '45a0c619bc70a6c956f3d00b1315475c4b86af40aede7e616d00f01a5d378475',
    idSymbol: 'ANTIGRAVITY_CLIENT_ID', secretSymbol: 'ANTIGRAVITY_CLIENT_SECRET',
  },
  'gemini-cli': {
    url: 'https://raw.githubusercontent.com/google-gemini/gemini-cli/fb972b2f87fe7d5b06d37eac711490162d98de2c/packages/core/src/code_assist/oauth2.ts',
    sha256: 'a3f8c55ad885656ed62144fb74e3f737117f58606a98c095f5e96f0707d9fd68',
    idSymbol: 'OAUTH_CLIENT_ID', secretSymbol: 'OAUTH_CLIENT_SECRET',
  },
});

export function parseRegistration(text, source, expectedId) {
  if (createHash('sha256').update(text).digest('hex') !== source.sha256) throw new UpstreamError(502, 'Native OAuth registration source integrity check failed');
  const scalar = symbol => new RegExp('\\b' + symbol + '\\s*=\\s*[\"\']([^\"\']+)[\"\']').exec(text)?.[1];
  const clientId = scalar(source.idSymbol), clientSecret = scalar(source.secretSymbol);
  if (clientId !== expectedId || !clientSecret || clientSecret.length > 256) throw new UpstreamError(502, 'Native OAuth registration does not match this provider client');
  return { clientId, clientSecret, sourceSha256: source.sha256 };
}

export async function registration(profile, store) {
  if (profile.clientSecret || !profile.registrationSource) return { ...profile };
  const source = registrationSources[profile.registrationSource];
  if (!source) throw new UpstreamError(500, 'Unknown native registration configuration');
  const cached = store.state.registrations[profile.registrationSource];
  if (cached?.clientId === profile.clientId && cached.sourceSha256 === source.sha256) return { ...profile, ...cached };
  const response = await open(source.url, { timeout: 10000 });
  if (response.statusCode !== 200) { await read(response, 1024 * 1024); throw new UpstreamError(502, 'Native OAuth registration source could not be retrieved'); }
  const values = parseRegistration(await read(response, 2 * 1024 * 1024), source, profile.clientId);
  store.state.registrations[profile.registrationSource] = values; store.save();
  return { ...profile, ...values };
}

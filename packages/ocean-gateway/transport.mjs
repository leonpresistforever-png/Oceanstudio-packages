// Direct Node HTTP transports preserve TLS verification and stream backpressure.
import http from 'node:http';
import https from 'node:https';
import { StringDecoder } from 'node:string_decoder';

export class UpstreamError extends Error {
  constructor(status, message, retryAfter) { super(message); this.status = status; this.retryAfter = retryAfter; }
}
export function safeEndpoint(value, local = false) {
  const url = new URL(value);
  if (url.username || url.password || url.hash || !['http:', 'https:'].includes(url.protocol)) throw Error('Invalid upstream URL');
  if (url.protocol !== 'https:' && !(local && ['127.0.0.1', 'localhost', '[::1]'].includes(url.hostname))) throw Error('Upstreams require HTTPS; local runtimes use loopback HTTP');
  return url;
}
export function open(url, { method = 'GET', headers = {}, body, signal, timeout = 180000 } = {}) {
  return new Promise((resolve, reject) => {
    const parsed = new URL(url), content = body === undefined ? null : Buffer.from(typeof body === 'string' ? body : JSON.stringify(body));
    const request = (parsed.protocol === 'https:' ? https : http).request(parsed, { method, headers: {
      ...headers, ...(content ? { 'Content-Length': content.length } : {}) }, signal }, resolve);
    request.setTimeout(timeout, () => request.destroy(Error('Upstream request timed out')));
    request.on('error', reject); request.end(content);
  });
}
export async function read(response, limit = 16 * 1024 * 1024) {
  const chunks = []; let size = 0;
  for await (const chunk of response) {
    size += chunk.length; if (size > limit) { response.destroy(); throw Error('Upstream response exceeded its size limit'); }
    chunks.push(chunk);
  }
  return Buffer.concat(chunks).toString('utf8');
}
export async function json(url, options = {}) {
  const response = await open(url, options), text = await read(response);
  let body; try { body = JSON.parse(text); } catch {
    if (response.statusCode >= 200 && response.statusCode < 300) throw new UpstreamError(502, 'Upstream returned invalid JSON');
    body = {};
  }
  if (response.statusCode < 200 || response.statusCode >= 300) {
    // Never return a provider's raw HTML or a URL containing an authorization code.
    const message = body.error?.message ?? (typeof body.error === 'string' ? body.error : body.message);
    throw new UpstreamError(response.statusCode, typeof message === 'string' ? message.slice(0, 500) : `Upstream HTTP ${response.statusCode}`, response.headers['retry-after']);
  }
  if (!body || typeof body !== 'object') throw Error('Upstream returned invalid JSON');
  return body;
}
export async function* events(response) {
  let buffer = ''; const decoder = new StringDecoder('utf8');
  for await (const chunk of response) {
    buffer += decoder.write(chunk);
    if (buffer.length > 4 * 1024 * 1024) throw Error('Upstream event exceeded its size limit');
    let boundary;
    while ((boundary = /\r?\n\r?\n/.exec(buffer))) {
      const frame = buffer.slice(0, boundary.index); buffer = buffer.slice(boundary.index + boundary[0].length);
      const data = frame.split(/\r?\n/).filter(l => l.startsWith('data:')).map(l => l.slice(5).replace(/^ /, '')).join('\n');
      if (data && data !== '[DONE]') yield JSON.parse(data);
    }
  }
  buffer += decoder.end();
  if (buffer.trim() && !buffer.trim().startsWith(':')) throw new UpstreamError(502, 'Upstream stream ended inside an event');
}

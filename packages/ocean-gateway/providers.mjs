// Ocean's provider adapters. Wire formats follow provider APIs, not another router's code.
import { randomUUID } from 'node:crypto';
import { json, open, read, events, safeEndpoint, UpstreamError } from './transport.mjs';

const flatten = content => typeof content === 'string' ? content : (content ?? []).filter(p => p.type === 'text').map(p => p.text).join('\n');
const urlAt = (base, path) => `${base.replace(/\/$/, '')}/${path.replace(/^\//, '')}`;
const common = token => ({ Authorization: `Bearer ${token}`, 'Content-Type': 'application/json', Accept: 'application/json' });
export const profiles = {
  antigravity: { clientId: '1071006060591-tmhssin2h21lcre235vtolojh4g403ep.apps.googleusercontent.com', clientSecret: process.env.OCEAN_ANTIGRAVITY_CLIENT_SECRET,
    registrationSource: 'antigravity',
    authorization: 'https://accounts.google.com/o/oauth2/v2/auth', token: 'https://oauth2.googleapis.com/token',
    userInfo: 'https://www.googleapis.com/oauth2/v1/userinfo', pkce: false,
    scope: 'https://www.googleapis.com/auth/cloud-platform https://www.googleapis.com/auth/userinfo.email https://www.googleapis.com/auth/userinfo.profile https://www.googleapis.com/auth/cclog https://www.googleapis.com/auth/experimentsandconfigs',
    baseUrl: 'https://daily-cloudcode-pa.googleapis.com', bootstrapUrl: 'https://cloudcode-pa.googleapis.com',
    alternateBaseUrls: ['https://cloudcode-pa.googleapis.com'] },
  codex: { clientId: 'app_EMoamEEZ73f0CkXaXp7hrann', authorization: 'https://auth.openai.com/oauth/authorize',
    token: 'https://auth.openai.com/oauth/token', scope: 'openid profile email offline_access', pkce: true,
    baseUrl: 'https://chatgpt.com/backend-api/codex', quotaUrl: 'https://chatgpt.com/backend-api/wham/usage' },
  'gemini-cli': { clientId: '681255809395-oo8ft2oprdrnp9e3aqf6av3hmdib135j.apps.googleusercontent.com',
    // Installed-application OAuth registration data published by Google's own CLI.
    clientSecret: process.env.OCEAN_GEMINI_CLIENT_SECRET, registrationSource: 'gemini-cli', authorization: 'https://accounts.google.com/o/oauth2/v2/auth',
    token: 'https://oauth2.googleapis.com/token', scope: 'https://www.googleapis.com/auth/cloud-platform https://www.googleapis.com/auth/userinfo.email https://www.googleapis.com/auth/userinfo.profile',
    pkce: true, baseUrl: 'https://cloudcode-pa.googleapis.com' },
};

export function responsesInput(messages) {
  const input = []; const instructions = [];
  for (const m of messages) {
    if (m.role === 'system' || m.role === 'developer') { instructions.push(flatten(m.content)); continue; }
    if (m.role === 'tool') { input.push({ type: 'function_call_output', call_id: m.tool_call_id, output: flatten(m.content) }); continue; }
    if (m.content) {
      const parts = typeof m.content === 'string' ? [{ type: 'text', text: m.content }] : m.content;
      input.push({ role: m.role, content: parts.map(p => p.type === 'image_url'
        ? { type: 'input_image', image_url: p.image_url.url }
        : { type: m.role === 'assistant' ? 'output_text' : 'input_text', text: p.text ?? '' }) });
    }
    for (const call of m.tool_calls ?? []) input.push({ type: 'function_call', call_id: call.id,
      name: call.function.name, arguments: call.function.arguments });
  }
  return { input, instructions: instructions.join('\n') };
}
function geminiBody(request) {
  const contents = [], system = [], toolNames = new Map();
  for (const m of request.messages) {
    if (['system', 'developer'].includes(m.role)) { system.push({ text: flatten(m.content) }); continue; }
    const parts = [];
    if (m.role === 'tool') {
      let response; try { response = JSON.parse(flatten(m.content)); } catch { response = { output: flatten(m.content) }; }
      parts.push({ functionResponse: { name: toolNames.get(m.tool_call_id) ?? m.name ?? m.tool_call_id, response } });
    } else {
      for (const p of typeof m.content === 'string' ? [{ type: 'text', text: m.content }] : m.content ?? []) {
        if (p.type === 'text') parts.push({ text: p.text });
        else if (p.type === 'image_url') {
          const match = /^data:([^;]+);base64,(.+)$/.exec(p.image_url.url);
          if (!match) throw Error('Gemini image requests require inline image data');
          parts.push({ inlineData: { mimeType: match[1], data: match[2] } });
        }
      }
      for (const c of m.tool_calls ?? []) {
        toolNames.set(c.id, c.function.name); parts.push({ functionCall: { name: c.function.name, args: JSON.parse(c.function.arguments || '{}') } });
      }
    }
    if (parts.length) contents.push({ role: m.role === 'assistant' ? 'model' : 'user', parts });
  }
  const generationConfig = {};
  for (const [from, to] of [['temperature', 'temperature'], ['top_p', 'topP'], ['max_tokens', 'maxOutputTokens']]) {
    if (request[from] !== undefined) generationConfig[to] = request[from];
  }
  return { contents, ...(system.length ? { systemInstruction: { parts: system } } : {}), generationConfig,
    ...(request.tools?.length ? { tools: [{ functionDeclarations: request.tools.map(t => ({ name: t.function.name,
      ...(t.function.description ? { description: t.function.description } : {}), parameters: t.function.parameters ?? { type: 'object', properties: {} } })) }] } : {}) };
}
function completion(model, content, calls, usage = {}, finishReason = 'stop') {
  return { id: 'chatcmpl-' + randomUUID(), object: 'chat.completion', created: Math.floor(Date.now() / 1000), model,
    choices: [{ index: 0, message: { role: 'assistant', content: content || null, ...(calls.length ? { tool_calls: calls } : {}) },
      finish_reason: calls.length ? 'tool_calls' : finishReason }], usage };
}
function geminiCompletion(model, body) {
  const response = body.response ?? body;
  const candidate = response.candidates?.[0];
  if (!candidate) throw new UpstreamError(502, response.promptFeedback?.blockReason ?? 'Provider returned no candidate');
  let content = ''; const calls = [];
  for (const p of candidate.content?.parts ?? []) {
    if (p.text && !p.thought) content += p.text;
    if (p.functionCall) calls.push({ id: 'call_' + randomUUID(), type: 'function', function: {
      name: p.functionCall.name, arguments: JSON.stringify(p.functionCall.args ?? {}) } });
  }
  const u = response.usageMetadata ?? {};
  return completion(model, content, calls, { prompt_tokens: u.promptTokenCount ?? 0, completion_tokens: u.candidatesTokenCount ?? 0,
    total_tokens: u.totalTokenCount ?? 0 }, candidate.finishReason === 'MAX_TOKENS' ? 'length' : 'stop');
}

export class Providers {
  constructor(store, configured = profiles) { this.store = store; this.profiles = configured; this.refreshes = new Map(); }
  async credential(account) {
    if (account.apiKey !== undefined) return account.apiKey;
    if (!account.tokens?.access_token) throw new UpstreamError(401, 'Account authorization is required');
    if (!account.tokens.expiresAt || account.tokens.expiresAt > Date.now() + 60000) return account.tokens.access_token;
    if (!account.tokens.refresh_token) throw new UpstreamError(401, 'Provider did not issue a refresh token');
    if (!this.refreshes.has(account.id)) this.refreshes.set(account.id, (async () => {
      const p = account.oauthClient ?? this.profiles[account.provider];
      const form = new URLSearchParams({ grant_type: 'refresh_token', refresh_token: account.tokens.refresh_token, client_id: p.clientId });
      if (p.clientSecret) form.set('client_secret', p.clientSecret);
      const next = await json(p.token, { method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, body: form.toString() });
      if (!next.access_token) throw new UpstreamError(502, 'Provider refresh did not return an access token');
      account.tokens = { ...account.tokens, ...next, expiresAt: Date.now() + Number(next.expires_in ?? 3600) * 1000 };
      this.store.save(); return next.access_token;
    })().finally(() => this.refreshes.delete(account.id)));
    return this.refreshes.get(account.id);
  }
  async headers(account) {
    const headers = common(await this.credential(account));
    if (account.provider === 'codex') {
      headers.originator = 'codex_cli_rs'; headers['User-Agent'] = 'OceanGateway/1.0';
      if (account.accountId) headers['ChatGPT-Account-Id'] = account.accountId;
    }
    if (account.format === 'anthropic') {
      delete headers.Authorization; headers['x-api-key'] = account.apiKey; headers['anthropic-version'] = '2023-06-01';
    }
    if (account.format === 'gemini') { delete headers.Authorization; headers['x-goog-api-key'] = account.apiKey; }
    return headers;
  }
  async bootstrap(account) {
    if (!['antigravity', 'gemini-cli'].includes(account.provider)) return;
    const base = account.bootstrapUrl ?? this.profiles[account.provider]?.bootstrapUrl ?? 'https://cloudcode-pa.googleapis.com';
    const data = await json(urlAt(base, 'v1internal:loadCodeAssist'), { method: 'POST', headers: await this.headers(account),
      body: { metadata: { ideType: 'IDE_UNSPECIFIED', platform: 'PLATFORM_UNSPECIFIED', pluginType: 'GEMINI' } } });
    const project = data.cloudaicompanionProject;
    account.project = typeof project === 'object' ? project.id : project;
    account.plan = data.paidTier?.name ?? data.currentTier?.name ?? data.paidTier?.id ?? data.currentTier?.id;
    if (!account.project) {
      const tiers = data.allowedTiers ?? []; const tier = tiers.find(t => t.isDefault)?.id ?? tiers[0]?.id;
      if (!tier) throw new UpstreamError(403, 'Provider has not granted this account a Code Assist project');
      const onboarding = { [account.provider === 'antigravity' ? 'tier_id' : 'tierId']: tier,
        metadata: { ideType: 'IDE_UNSPECIFIED', platform: 'PLATFORM_UNSPECIFIED', pluginType: 'GEMINI' } };
      const enrolled = await json(urlAt(base, 'v1internal:onboardUser'), { method: 'POST', headers: await this.headers(account), body: onboarding });
      let status = enrolled;
      for (let i = 0; !status.done && i < 20; i++) {
        await new Promise(resolve => setTimeout(resolve, 1000));
        status = account.provider === 'antigravity' || !status.name
          ? await json(urlAt(base, 'v1internal:onboardUser'), { method: 'POST', headers: await this.headers(account), body: onboarding })
          : await json(urlAt(base, 'v1internal/' + status.name.replace(/^\//, '')), { headers: await this.headers(account) });
      }
      const response = status.response?.cloudaicompanionProject;
      account.project = typeof response === 'object' ? response.id : response;
      if (!status.done || !account.project) throw new UpstreamError(503, 'Provider project provisioning has not completed');
    }
    this.store.save();
  }
  async models(account) {
    const headers = await this.headers(account);
    let result, rows;
    if (['antigravity', 'gemini-cli'].includes(account.provider)) {
      if (!account.project) await this.bootstrap(account);
      let failure;
      for (const base of [account.baseUrl, ...(this.profiles[account.provider]?.alternateBaseUrls ?? [])]) {
        for (const method of ['fetchAvailableModels', 'models']) {
          try {
            result = await json(urlAt(base, 'v1internal:' + method), { method: 'POST', headers, body: { project: account.project } });
            if (result.models && Object.keys(result.models).length) { account.baseUrl = base; break; }
          } catch (error) { failure = error; }
        }
        if (result?.models && Object.keys(result.models).length) break;
      }
      if (!result?.models) throw failure ?? new UpstreamError(502, 'Provider returned no available models');
      rows = Array.isArray(result.models) ? result.models : Object.entries(result.models ?? {}).map(([id, value]) => ({ ...value, id }));
    } else if (account.provider === 'codex') {
      result = await json(urlAt(account.baseUrl, 'models?client_version=0.116.0'), { headers });
      rows = result.models ?? result.data ?? [];
    } else {
      result = await json(urlAt(account.baseUrl, 'models'), { headers }); rows = result.data ?? result.models ?? [];
    }
    const models = rows.map(m => ({ id: m.id ?? m.slug ?? m.name?.replace(/^models\//, ''), name: m.displayName ?? m.display_name ?? m.name ?? m.id ?? m.slug,
      context_length: m.context_length ?? m.context_window ?? m.inputTokenLimit ?? 0,
      supportsTools: Boolean(m.supportsTools ?? m.supports_function_calling), supportsVision: Boolean(m.supportsVision ?? m.supports_image_input) })).filter(m => typeof m.id === 'string' && m.id);
    if (!models.length) throw new UpstreamError(502, 'Provider returned an empty model catalogue');
    account.models = models; this.store.save(); return models;
  }
  async quota(account) {
    if (account.provider === 'codex') {
      const raw = await json(this.profiles.codex.quotaUrl, { headers: await this.headers(account) });
      const quotas = {};
      for (const [name, field] of [['session', 'primary_window'], ['weekly', 'secondary_window']]) {
        const window = raw.rate_limit?.[field], used = window?.used_percent;
        if (typeof used === 'number' && used >= 0 && used <= 100) quotas[name] = {
          usedPercentage: used, remainingPercentage: 100 - used, fractionReported: true,
          ...(Number.isFinite(window.reset_at) ? { resetAt: new Date(window.reset_at * 1000).toISOString() } : {}) };
      }
      return { plan: raw.plan_type ?? '', planName: raw.plan_type ?? '', quotas, raw, source: 'provider' };
    }
    if (['antigravity', 'gemini-cli'].includes(account.provider)) {
      if (!account.project) await this.bootstrap(account);
      const raw = await json(urlAt(account.baseUrl, 'v1internal:retrieveUserQuota'), { method: 'POST', headers: await this.headers(account), body: { project: account.project } });
      const quotas = {};
      for (const b of raw.buckets ?? []) if (b.modelId) quotas[b.modelId] = {
        ...(Number.isFinite(b.remainingFraction) ? { remainingPercentage: b.remainingFraction * 100 } : {}),
        resetAt: b.resetTime, fractionReported: Number.isFinite(b.remainingFraction) };
      return { plan: account.plan ?? '', planName: account.plan ?? '', quotas, raw, source: 'provider' };
    }
    // No invented credit limit for API-key and local-runtime accounts.
    return { source: 'provider', available: false, planName: '' };
  }
  async request(account, model, request, signal) {
    const headers = await this.headers(account);
    if (account.provider === 'codex') {
      const body = { model, ...responsesInput(request.messages), stream: true, store: false,
        ...(request.tools ? { tools: request.tools.map(t => ({ type: 'function', ...t.function })) } : {}) };
      return { format: 'responses', response: await open(urlAt(account.baseUrl, 'responses'), { method: 'POST', headers, body, signal }) };
    }
    if (['antigravity', 'gemini-cli'].includes(account.provider) || account.format === 'gemini') {
      if (!account.project && account.format !== 'gemini') await this.bootstrap(account);
      const body = geminiBody(request), localStream = request.stream === true;
      const method = localStream ? 'streamGenerateContent' : 'generateContent';
      const url = account.format === 'gemini' ? urlAt(account.baseUrl, `models/${encodeURIComponent(model)}:${method}${localStream ? '?alt=sse' : ''}`)
        : urlAt(account.baseUrl, `v1internal:${method}${localStream ? '?alt=sse' : ''}`);
      return { format: 'gemini', response: await open(url, { method: 'POST', headers, signal,
        body: account.format === 'gemini' ? body : { project: account.project, model, request: body,
          ...(account.provider === 'antigravity' ? { userAgent: 'antigravity', requestType: 'agent', requestId: randomUUID() } : {}) } }) };
    }
    if (account.format === 'anthropic') {
      const system = request.messages.filter(m => ['system', 'developer'].includes(m.role)).map(m => flatten(m.content)).join('\n');
      const messages = request.messages.filter(m => !['system', 'developer'].includes(m.role)).map(m => {
        if (m.role === 'tool') return { role: 'user', content: [{ type: 'tool_result', tool_use_id: m.tool_call_id, content: flatten(m.content) }] };
        const content = flatten(m.content) ? [{ type: 'text', text: flatten(m.content) }] : [];
        for (const call of m.tool_calls ?? []) content.push({ type: 'tool_use', id: call.id, name: call.function.name, input: JSON.parse(call.function.arguments) });
        return { role: m.role, content };
      });
      const body = { model, messages, max_tokens: request.max_tokens ?? 1024, stream: Boolean(request.stream), ...(system ? { system } : {}),
        ...(request.tools?.length ? { tools: request.tools.map(t => ({ name: t.function.name, description: t.function.description, input_schema: t.function.parameters })) } : {}) };
      return { format: 'anthropic', response: await open(urlAt(account.baseUrl, 'messages'), { method: 'POST', headers, body, signal }) };
    }
    safeEndpoint(account.baseUrl, account.authType === 'local');
    return { format: 'openai', response: await open(urlAt(account.baseUrl, 'chat/completions'), {
      method: 'POST', headers, body: { ...request, model }, signal }) };
  }
  async collect(format, response, model) {
    if (format === 'responses') {
      let completed;
      for await (const event of events(response)) {
        if (event.type === 'response.completed') completed = event.response;
        if (['error', 'response.failed'].includes(event.type)) throw new UpstreamError(502, event.message ?? event.response?.error?.message ?? 'Provider generation failed');
      }
      if (!completed) throw new UpstreamError(502, 'Provider stream ended before completion');
      const text = (completed.output ?? []).filter(v => v.type === 'message').flatMap(v => v.content ?? []).filter(v => v.type === 'output_text').map(v => v.text).join('');
      const calls = (completed.output ?? []).filter(v => v.type === 'function_call').map(v => ({ id: v.call_id, type: 'function', function: { name: v.name, arguments: v.arguments } }));
      const u = completed.usage ?? {};
      return completion(model, text, calls, { prompt_tokens: u.input_tokens ?? 0, completion_tokens: u.output_tokens ?? 0, total_tokens: u.total_tokens ?? 0 });
    }
    const body = JSON.parse(await read(response));
    if (format === 'gemini') return geminiCompletion(model, body);
    if (format === 'anthropic') {
      const content = (body.content ?? []).filter(p => p.type === 'text').map(p => p.text).join('');
      const calls = (body.content ?? []).filter(p => p.type === 'tool_use').map(p => ({ id: p.id, type: 'function', function: { name: p.name, arguments: JSON.stringify(p.input) } }));
      return completion(model, content, calls, { prompt_tokens: body.usage?.input_tokens ?? 0, completion_tokens: body.usage?.output_tokens ?? 0,
        total_tokens: (body.usage?.input_tokens ?? 0) + (body.usage?.output_tokens ?? 0) }, body.stop_reason === 'max_tokens' ? 'length' : 'stop');
    }
    return body;
  }
  async* stream(format, response, model) {
    const id = 'chatcmpl-' + randomUUID();
    const chunk = (delta, reason = null) => ({ id, object: 'chat.completion.chunk', created: Math.floor(Date.now() / 1000), model,
      choices: [{ index: 0, delta, finish_reason: reason }] });
    if (format === 'openai') { for await (const e of events(response)) yield e; return; }
    yield chunk({ role: 'assistant' });
    const calls = new Map(); let completed = false;
    for await (const e of events(response)) {
      if (format === 'responses') {
        if (e.type === 'response.output_text.delta') yield chunk({ content: e.delta });
        if (e.type === 'response.output_item.added' && e.item?.type === 'function_call') {
          const index = calls.size; calls.set(e.item.id, index);
          yield chunk({ tool_calls: [{ index, id: e.item.call_id, type: 'function', function: { name: e.item.name, arguments: '' } }] });
        }
        if (e.type === 'response.function_call_arguments.delta') yield chunk({ tool_calls: [{ index: calls.get(e.item_id) ?? 0, function: { arguments: e.delta } }] });
        if (['error', 'response.failed'].includes(e.type)) throw new UpstreamError(502, 'Provider generation failed');
        if (e.type === 'response.completed') { completed = true; yield chunk({}, calls.size ? 'tool_calls' : 'stop'); }
      } else if (format === 'gemini') {
        const out = geminiCompletion(model, e), m = out.choices[0].message;
        if (m.content) yield chunk({ content: m.content });
        if (m.tool_calls) yield chunk({ tool_calls: m.tool_calls.map((c, index) => ({ ...c, index })) });
        if ((e.response ?? e).candidates?.[0]?.finishReason) yield chunk({}, out.choices[0].finish_reason);
      } else if (format === 'anthropic') {
        if (e.type === 'content_block_start' && e.content_block?.type === 'tool_use') yield chunk({ tool_calls: [{ index: e.index,
          id: e.content_block.id, type: 'function', function: { name: e.content_block.name, arguments: '' } }] });
        if (e.type === 'content_block_delta' && e.delta?.type === 'text_delta') yield chunk({ content: e.delta.text });
        if (e.type === 'content_block_delta' && e.delta?.type === 'input_json_delta') yield chunk({ tool_calls: [{ index: e.index, function: { arguments: e.delta.partial_json } }] });
        if (e.type === 'error') throw new UpstreamError(502, e.error?.message ?? 'Provider generation failed');
        if (e.type === 'message_delta') yield chunk({}, e.delta.stop_reason === 'tool_use' ? 'tool_calls' : e.delta.stop_reason === 'max_tokens' ? 'length' : 'stop');
      }
    }
    if (format === 'responses' && !completed) throw new UpstreamError(502, 'Provider stream ended before completion');
  }
}

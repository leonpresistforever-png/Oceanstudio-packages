# Ocean Gateway

An independent local server written for Ocean using Node's built-in HTTP, TLS and
cryptography modules. It does not install, execute, vendor or depend on OmniRoute.
All provider adapters in this directory are Ocean implementations. Native OAuth
registration identifiers and wire formats follow the corresponding provider
clients; these identifiers are not private user credentials.

Google's installed-app token exchange requires native client registration data.
The repository contains no client-secret value. At first authorization, Ocean
retrieves two registration constants from a SHA-256-pinned open-source reference
(Google's own CLI for Gemini; the published Antigravity auth registration for
Antigravity), checks the expected client ID, and caches them encrypted in private
state. Downloaded source is never executed or shipped as gateway code. There is
no OmniRoute download or installation. An operator may instead provide the
registration through `OCEAN_GEMINI_CLIENT_SECRET` or
`OCEAN_ANTIGRAVITY_CLIENT_SECRET` in the private environment.

```sh
pkg install ocean-gateway
ocean-gateway start
ocean-gateway connect codex
ocean-gateway connect antigravity
ocean-gateway connect gemini-cli
# For an already running Ollama or other OpenAI-compatible local runtime:
ocean-gateway add-local http://127.0.0.1:11434/v1
ocean-gateway status
ocean-gateway stop
```

`connect` and `add-local` start the server first. Browser authorization uses a
bound loopback listener, random state, a one-use expiring transaction and the
native client's callback contract. Codex uses S256 PKCE and its registered
`http://localhost:1455/auth/callback`. The Google clients use their own native
OAuth registration and grant contract. A provider that does not support PKCE
is not labelled as PKCE. No token, code or callback URL is pasted manually.

The server listens only on `127.0.0.1:20129`. `/v1/models` discovers models from
connected accounts. `/v1/chat/completions` supports ordinary and streamed
inference, function calls, provider wire translation and configured priority
fallback on account limits or upstream failures before streaming begins.
Supported wire formats are OpenAI chat, OpenAI Responses for Codex accounts,
Gemini and Anthropic messages. This release does not advertise an unimplemented
public `/v1/responses` route. Local Ollama models use the real runtime's `/v1`.

Management endpoints require a private generated session; inference requires an
account-scoped generated key. A management cookie cannot authorize inference.
Account tokens, refresh credentials and API keys are stored using AES-256-GCM;
private files and directories have modes 0600 and 0700. Refresh uses the OAuth
registration that issued the original credential. The terminal writes its
inference configuration to the private `terminal-client.json`, not stdout.
Deleting an account removes its access from existing inference keys.

Provider model lists, subscription plans and quota readings come from upstream
responses. The gateway does not create subscription benefits or quotas. No
static model catalogue or successful connection is invented. Provider consent
and account entitlements still need verification on the user's device; the
automated tests exercise real HTTP requests against deterministic test servers,
including token exchange, replay rejection, transport translation and fallback.

Original code: MIT. Protocol research receipts are in
`sources/runtime-dependencies/protocols.json`. Tests:
`node --test tests/test-independent-gateway.mjs`.

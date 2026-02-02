# Plan: Credential Injection via ANTHROPIC_BASE_URL

## Summary

Use Claude Code's native `ANTHROPIC_BASE_URL` environment variable to route API traffic through the gateway for credential injection in both public and private modes. This supersedes the analysis in PR #699.

## Context

Claude Code officially supports custom API endpoints via `ANTHROPIC_BASE_URL` ([docs](https://code.claude.com/docs/en/llm-gateway)). This enables a clean architecture where:

1. **Public mode**: Container has direct internet access, but Anthropic API calls route through gateway
2. **Private mode**: All traffic routes through gateway proxy (existing behavior)

Both modes use the same credential injection mechanism, simplifying the architecture.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           PUBLIC MODE                                    │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌─────────────────┐    ANTHROPIC_BASE_URL     ┌─────────────────────┐  │
│  │  jib-container  │ ─────────────────────────▶│    jib-gateway      │  │
│  │                 │   http://jib-gateway:9847 │                     │  │
│  │  Claude Code    │   /v1/messages            │  Gateway API :9847  │──┼──▶ api.anthropic.com
│  │                 │                           │  - Inject creds     │  │
│  └────────┬────────┘                           │  - Forward request  │  │
│           │                                    └─────────────────────┘  │
│           │ Direct internet                                              │
│           ▼                                                              │
│     npm, pypi, github, web search, etc.                                  │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                          PRIVATE MODE                                    │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌─────────────────┐    ANTHROPIC_BASE_URL     ┌─────────────────────┐  │
│  │  jib-container  │ ─────────────────────────▶│    jib-gateway      │  │
│  │                 │   http://jib-gateway:9847 │                     │  │
│  │  Claude Code    │   /v1/messages            │  Gateway API :9847  │──┼──▶ api.anthropic.com
│  │                 │                           │  - Inject creds     │  │
│  └────────┬────────┘                           │  - Forward request  │  │
│           │                                    │                     │  │
│           │ HTTPS_PROXY                        │  Squid Proxy :3128  │──┼──▶ allowlist only
│           ▼                                    │  - Domain filtering │  │
│     ┌─────────────────────────────────────────▶│  - Audit logging    │  │
│     │  All other traffic                       └─────────────────────┘  │
│     │                                                                    │
└─────────────────────────────────────────────────────────────────────────┘
```

## Key Insight: No More SSL Bump for Anthropic

With `ANTHROPIC_BASE_URL`, Claude Code sends requests directly to our gateway over HTTP (internal network), not to `api.anthropic.com` over HTTPS. This means:

- **No SSL bump needed** for Anthropic API traffic
- **No CA certificate trust** required in container for Anthropic traffic
- **Simpler Squid config** - only needs to allow traffic, not MITM it
- **Gateway handles TLS** outbound to real api.anthropic.com

The gateway receives the plaintext request, adds credentials, then makes an authenticated HTTPS request to Anthropic.

## Implementation Plan

### Phase 1: Gateway Anthropic Proxy Endpoint

Add an HTTP endpoint to the gateway that proxies requests to Anthropic with credential injection.

**File: `gateway-sidecar/gateway.py`**

```python
# New endpoint: POST /v1/messages
# - Receives Claude Code's messages request (over internal HTTP)
# - Injects authentication header from credentials manager
# - Forwards to api.anthropic.com over HTTPS
# - Returns response to Claude Code

@app.route('/v1/messages', methods=['POST'])
async def proxy_anthropic_messages():
    # Get credentials from existing anthropic_credentials.py
    auth_header = credentials_manager.get_auth_header()

    # Forward to Anthropic with injected auth
    async with httpx.AsyncClient() as client:
        response = await client.post(
            'https://api.anthropic.com/v1/messages',
            headers={
                'Authorization': auth_header,
                'anthropic-version': request.headers.get('anthropic-version'),
                'anthropic-beta': request.headers.get('anthropic-beta'),
                **filtered_headers(request.headers),
            },
            content=await request.get_data(),
        )
    return response.content, response.status_code, dict(response.headers)

# Also need: /v1/messages/count_tokens (same pattern)
```

### Phase 2: Container Environment Configuration

**File: `jib-container/entrypoint.py`**

```python
def setup_anthropic_api(config: Config, logger: Logger) -> None:
    """Configure Claude Code to use gateway for Anthropic API."""
    gateway_url = "http://jib-gateway:9847"

    # Set ANTHROPIC_BASE_URL to route API calls through gateway
    os.environ["ANTHROPIC_BASE_URL"] = gateway_url

    # Remove any ANTHROPIC_API_KEY from container environment
    # Credentials are held by gateway only
    if "ANTHROPIC_API_KEY" in os.environ:
        del os.environ["ANTHROPIC_API_KEY"]
    if "ANTHROPIC_OAUTH_TOKEN" in os.environ:
        del os.environ["ANTHROPIC_OAUTH_TOKEN"]

    logger.success(f"Anthropic API routed through gateway: {gateway_url}")
```

### Phase 3: Simplify Squid Configuration

**Private mode (`squid.conf`):**
- Remove SSL bump for api.anthropic.com (no longer needed)
- Keep domain allowlist filtering
- Keep SSL bump for peek/splice (SNI inspection)

**Public mode (`squid-allow-all.conf`):**
- No changes needed (already allows all traffic)
- Anthropic API traffic goes directly to gateway, not through Squid

### Phase 4: Remove Container CA Trust (Cleanup)

With ANTHROPIC_BASE_URL, the container no longer needs to trust the gateway CA for Anthropic traffic:

- Keep CA trust for private mode (other HTTPS traffic through proxy)
- Can simplify public mode (no proxy, no CA trust needed)

## Files to Modify

| File | Change |
|------|--------|
| `gateway-sidecar/gateway.py` | Add `/v1/messages` and `/v1/messages/count_tokens` proxy endpoints |
| `jib-container/entrypoint.py` | Set `ANTHROPIC_BASE_URL`, remove API key from container env |
| `gateway-sidecar/squid.conf` | Remove SSL bump for api.anthropic.com |
| `docs/adr/` | Document the credential injection architecture |

## Benefits Over Previous Approach

1. **Simpler**: No SSL MITM complexity for Anthropic traffic
2. **Officially supported**: Uses Claude Code's documented configuration
3. **More secure**: Credentials never in container environment
4. **Unified**: Same approach works for both public and private modes
5. **No NET_ADMIN**: Doesn't require special container capabilities
6. **Better debugging**: HTTP traffic between container and gateway is inspectable

## Claude Code Requirements

Based on [LLM Gateway docs](https://code.claude.com/docs/en/llm-gateway):

### Required Headers to Forward

The gateway must forward these headers from Claude Code:
- `anthropic-version`
- `anthropic-beta`

### Endpoints to Implement

1. `POST /v1/messages` - Main messages API
2. `POST /v1/messages/count_tokens` - Token counting

### Authentication

Gateway injects either:
- `Authorization: Bearer <token>` (for OAuth)
- `x-api-key: <key>` (for API key)

## Testing Plan

1. **Unit tests**: Gateway proxy endpoint with mocked Anthropic responses
2. **Integration tests**:
   - Public mode: Claude Code can call API through gateway
   - Private mode: Same behavior
   - Credentials not visible in container environment
   - Gateway logs show injected authentication
3. **E2E tests**:
   - Full conversation with Claude Code in both modes
   - Verify responses are received correctly

## Migration Path

### From Current State (PR #698 merged)

1. Add gateway proxy endpoints (non-breaking)
2. Set ANTHROPIC_BASE_URL in container (takes precedence over direct API)
3. Verify both modes work
4. Remove SSL bump for api.anthropic.com from squid.conf
5. Clean up unused CA trust code for public mode

### Rollback

If issues arise:
1. Remove ANTHROPIC_BASE_URL from container env
2. Restore SSL bump in squid.conf
3. Container falls back to direct API calls with injected creds via MITM

## Open Questions

1. **Streaming responses**: Does httpx handle Server-Sent Events correctly for message streaming?
2. **Error handling**: How should gateway proxy errors be reported to Claude Code?
3. **Health checks**: Should gateway health include Anthropic API reachability?

## References

- [Claude Code LLM Gateway docs](https://code.claude.com/docs/en/llm-gateway)
- [Claude Code Network Config](https://code.claude.com/docs/en/network-config)
- [Claude Code Settings](https://code.claude.com/docs/en/settings)
- PR #698: Phase 1 SSL bump (merged)
- PR #699: Original public mode analysis (superseded by this plan)
- PR #700: ICAP credential injection (in progress)

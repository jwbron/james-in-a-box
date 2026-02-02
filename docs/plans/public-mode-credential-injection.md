# Plan: Public Mode Credential Injection

## Context

PR #698 implements SSL bump for credential injection in **private mode** only. In private mode, all traffic goes through the gateway proxy (`HTTPS_PROXY` is set), enabling the gateway to MITM `api.anthropic.com` and inject authentication headers.

**Problem:** In public mode, containers have direct internet access without using the proxy. The Anthropic API traffic bypasses the gateway entirely, so credentials cannot be injected.

**Goal:** Enable credential injection for `api.anthropic.com` in public mode while preserving direct internet access for other traffic.

## Options Analysis

### Option 1: Proxy for Anthropic API Only (Recommended)

Configure Claude Code to route Anthropic API traffic through the gateway while other traffic goes direct.

**Implementation:**
```bash
# In container entrypoint for public mode
export ANTHROPIC_BASE_URL="http://jib-gateway:3128/anthropic-proxy"
# OR if Claude Code supports a proxy-per-host config:
export ANTHROPIC_PROXY="http://jib-gateway:3128"
```

**Pros:**
- Minimal change to container networking
- No special capabilities required
- Application-level, easy to debug

**Cons:**
- Requires Claude Code to support custom base URL or proxy
- Need to verify Claude Code configuration options

**Investigation needed:**
- [ ] Check if Claude Code supports `ANTHROPIC_BASE_URL` or similar
- [ ] Check if Claude Code supports per-host proxy configuration
- [ ] Review Anthropic SDK documentation for proxy support

### Option 2: iptables Transparent Redirect

Use iptables in the container to redirect `api.anthropic.com:443` traffic to the gateway.

**Implementation:**
```bash
# In container entrypoint for public mode
# Resolve api.anthropic.com IPs and redirect to gateway
ANTHROPIC_IPS=$(getent hosts api.anthropic.com | awk '{print $1}')
for ip in $ANTHROPIC_IPS; do
    iptables -t nat -A OUTPUT -p tcp -d "$ip" --dport 443 \
        -j DNAT --to-destination jib-gateway:3128
done
```

**Pros:**
- Transparent to applications
- Works with any Claude Code version
- No application configuration needed

**Cons:**
- Requires `NET_ADMIN` capability (security concern)
- IP-based, may break if Anthropic changes IPs
- More complex to debug
- iptables rules can conflict with Docker networking

### Option 3: DNS Override + Gateway Listener

Override DNS for `api.anthropic.com` to point to the gateway, with a dedicated listener.

**Implementation:**
1. Gateway listens on port 443 for `api.anthropic.com`
2. Container's `/etc/hosts` overrides: `172.30.0.2 api.anthropic.com`
3. Gateway accepts TLS, injects headers, proxies to real Anthropic

```bash
# In container /etc/hosts
172.30.0.2  api.anthropic.com

# Gateway needs additional listener on :443
# Certificate must be for api.anthropic.com (trusted via CA)
```

**Pros:**
- Transparent to applications
- No special container capabilities
- Works with any application

**Cons:**
- Gateway needs to listen on 443 (port collision potential)
- Requires separate certificate generation for api.anthropic.com
- DNS override affects all processes in container
- More complex gateway configuration

### Option 4: Always Use Proxy (Simplest)

Set `HTTPS_PROXY` in all modes, but configure allowed domains in public mode.

**Implementation:**
```bash
# Both private and public mode
export HTTPS_PROXY="http://jib-gateway:3128"
export HTTP_PROXY="http://jib-gateway:3128"
# Public mode: proxy allows all domains but bumps only api.anthropic.com
# Private mode: proxy restricts to allowlist and bumps api.anthropic.com
```

**Pros:**
- Simplest implementation
- Consistent behavior across modes
- Gateway already supports both configs (squid.conf vs squid-allow-all.conf)

**Cons:**
- All traffic routed through proxy (slight latency)
- Public mode loses "direct" internet feel
- Some tools may not respect proxy settings

## Recommendation

**Option 1** is the cleanest if Claude Code supports it. Fallback to **Option 4** if not.

**Immediate next step:** Investigate Claude Code's proxy/base URL configuration options before implementing.

## Investigation Tasks

1. **Claude Code config analysis:**
   - [ ] Check Anthropic SDK for proxy support (`httpx` backend has proxy support)
   - [ ] Check if `ANTHROPIC_BASE_URL` environment variable is respected
   - [ ] Review Claude Code source for API client configuration

2. **If Option 1 viable:**
   - [ ] Add conditional logic to container entrypoint for public mode
   - [ ] Set appropriate env vars to route Anthropic traffic through gateway
   - [ ] Update squid-allow-all.conf to also perform SSL bump for api.anthropic.com

3. **If Option 4 needed:**
   - [ ] Always set `HTTPS_PROXY` in container entrypoint
   - [ ] Ensure squid-allow-all.conf has SSL bump for api.anthropic.com
   - [ ] Test that general internet access still works

## Files to Modify

| File | Change |
|------|--------|
| `gateway-sidecar/squid-allow-all.conf` | Add SSL bump for api.anthropic.com |
| `jib-container/entrypoint.py` | Set proxy or base URL for Anthropic in public mode |
| `docs/adr/` | Document credential injection architecture |

## Testing

1. Start container in public mode
2. Verify general internet access works (curl example.com)
3. Verify Claude Code can connect to Anthropic API
4. Check gateway logs to confirm credential injection header added
5. Verify no credentials leaked in container environment
6. **ICAP failure scenario:** Stop the ICAP server and verify requests fail gracefully:
   - Requests should reach Anthropic (fail-open behavior)
   - Anthropic should return 401 Unauthorized (clear error feedback)
   - Verify no hangs or timeouts from Squid
   - Restart ICAP server and verify recovery

# Squid ssl_bump and CONNECT Denial: Why HTTP 403 Doesn't Work

## Summary

When Squid is configured with `ssl-bump` on the `http_port`, `http_access deny CONNECT` rules are **bypassed**. Squid always accepts CONNECT requests to perform the ssl_bump operation, making it impossible to return HTTP 403 for blocked HTTPS domains.

This document explains why, documents the testing evidence, and discusses alternatives.

## Background

PR #650 attempted to improve the user experience when HTTPS domains are blocked by network lockdown. The goal was to return a clear HTTP 403 with an error page instead of confusing SSL certificate errors.

The approach was to add:
```
http_access deny CONNECT !allowed_domains
```

Before the `http_access allow CONNECT` rule, expecting Squid to deny the CONNECT at the HTTP level.

## The Problem

### How ssl_bump Works

When `ssl-bump` is configured on Squid's `http_port`, the proxy has a special processing path for HTTPS (CONNECT) requests:

1. **CONNECT request arrives** - Client sends `CONNECT example.com:443 HTTP/1.1`
2. **Squid accepts CONNECT** - Returns `200 Connection established` to start TLS
3. **ssl_bump peek** - Squid reads the TLS ClientHello to extract SNI (hostname)
4. **ssl_bump decision** - Based on SNI, Squid decides to `splice` (allow) or `terminate` (block)

The critical point: **Step 2 happens before Step 3**. Squid must accept the CONNECT to perform SNI inspection. The `http_access deny CONNECT` rule is evaluated, but ssl_bump overrides it because the TLS inspection requires the connection to be established first.

### Evidence from Testing

| Request Type | ACL Type | Expected | Actual | Working? |
|--------------|----------|----------|--------|----------|
| `http://example.com` | dstdomain | 403 | 403 | Yes |
| `http://93.184.216.34` | url_regex (IP) | 403 | 403 | Yes |
| `CONNECT example.com:443` | dstdomain | 403 | **200** | **No** |
| `CONNECT api.anthropic.com:443` | dstdomain | 200 | 200 | Yes |

The `dstdomain` ACL works correctly for:
- Regular HTTP requests (non-CONNECT)
- All other http_access rules (IP blocking, etc.)

But it does **not** work for CONNECT denial when ssl_bump is enabled.

### Raw Test Output

```bash
# CONNECT to blocked domain - should be 403, actually 200
$ printf "CONNECT example.com:443 HTTP/1.1\r\nHost: example.com:443\r\n\r\n" | nc jib-gateway 3128
HTTP/1.1 200 Connection established

# HTTP to blocked domain - correctly returns 403
$ curl -x http://jib-gateway:3128 http://example.com/
HTTP/1.1 403 Forbidden
```

## Why This Is a Squid Architectural Limitation

The issue is fundamental to how ssl_bump works:

1. **SNI is in the TLS layer** - The hostname is in the TLS ClientHello, which comes AFTER the TCP connection is established

2. **CONNECT establishes the TCP tunnel** - Squid must accept CONNECT to receive the TLS handshake

3. **http_access evaluates at HTTP layer** - The deny rule fires at the wrong time

This is not a bug or misconfiguration - it's how ssl_bump is designed. The Squid documentation states:

> When ssl-bump is configured, Squid accepts the CONNECT request and then starts the SSL handshake as configured. The ssl_bump directives determine what happens next.

## Current Behavior (ssl_bump terminate)

When a blocked domain is accessed via HTTPS:

1. Squid accepts CONNECT (returns 200)
2. Squid peeks at TLS ClientHello, extracts SNI
3. SNI doesn't match `allowed_domains`
4. `ssl_bump terminate` executes
5. Squid presents a self-signed certificate to signal rejection
6. Client sees: `SSL certificate problem: self-signed certificate`

This is confusing but **functional** - the connection is blocked.

## Alternatives Considered

### 1. Two-Port Architecture

Run two `http_port` listeners:
- Port 3128: ssl-bump enabled for allowed domains
- Port 3129: No ssl-bump, http_access deny for blocked domains

**Problems:**
- Requires client-side routing logic to choose port based on destination
- Adds significant complexity
- Defeats the purpose of transparent proxying

### 2. External ACL Helper

Use `external_acl_type` to call a script that determines allow/deny before ssl_bump.

**Problems:**
- Still subject to same limitation - CONNECT accepted before helper called for ssl_bump
- Adds latency and complexity

### 3. Transparent Proxy Mode

Use iptables/nftables to intercept traffic transparently.

**Problems:**
- Requires root/privileged container
- Complex networking setup
- May not work in all Docker network configurations

### 4. Accept the SSL Error (Current Approach)

Keep `ssl_bump terminate` for blocked domains. The SSL error is confusing but:
- The connection IS blocked (security goal met)
- Can document the expected behavior
- Can add client-side tooling to interpret the error

**This is the recommended approach** given the constraints.

## Recommendations

### Short Term

1. **Revert PR #650** - The http_access deny CONNECT approach doesn't work
2. **Document the expected behavior** - Users should expect SSL errors for blocked HTTPS
3. **Consider client-side tooling** - Could detect the self-signed cert pattern and show better errors

### Long Term

1. **Evaluate alternative proxies** - Some proxies may handle this differently
2. **Consider transparent mode** - If network architecture supports it
3. **Accept the limitation** - SSL errors for blocked HTTPS is the standard behavior for most corporate proxies with ssl_bump

## References

- [Squid ssl_bump documentation](http://www.squid-cache.org/Doc/config/ssl_bump/)
- [Squid SSL Peek and Splice](https://wiki.squid-cache.org/Features/SslPeekAndSplice)
- PR #650: Original attempt to fix this
- PR #657: Revert of PR #650

## Testing Commands

To reproduce the testing:

```bash
# Test CONNECT to blocked domain (should see 200, then SSL error)
curl -v https://example.com 2>&1 | head -20

# Test HTTP to blocked domain (should see 403)
curl -v -x http://jib-gateway:3128 http://example.com/

# Test direct IP (should see 403)
curl -v -x http://jib-gateway:3128 http://93.184.216.34/

# Raw CONNECT test
printf "CONNECT example.com:443 HTTP/1.1\r\nHost: example.com:443\r\n\r\n" | timeout 5 nc jib-gateway 3128
```

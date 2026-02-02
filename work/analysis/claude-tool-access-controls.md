# Analysis: Claude Tool Access Controls (Pre-Work for Egg Extraction)

**Status:** Analysis
**Date:** 2026-02-02
**Related:** PR #693 (Sandbox Extraction Proposal), PR #686 (Security Testing)
**Task:** beads-5u3tp

---

## Executive Summary

This document analyzes the "Claude Tool Access Controls" pre-work item identified in PR #693 (Sandbox Extraction Proposal). The requirement stems from security findings in PR #686: Claude's WebSearch and WebFetch tools bypass container network controls because they route through Anthropic's API infrastructure, creating a potential data exfiltration vector in private mode.

**Key finding:** This pre-work cannot be fully resolved at the infrastructure level alone. It requires understanding Claude Code's tool architecture and potentially coordinating with Anthropic for API-level controls.

---

## Background

### The Security Gap

PR #686's security testing revealed that in private mode (`PRIVATE_MODE=true`):

| Control | Status |
|---------|--------|
| Network lockdown (curl, wget, etc.) | Effective |
| GitHub access control | Effective |
| Credential isolation | Effective |
| DNS lockdown | Effective |
| **WebSearch tool** | **Bypasses controls** |
| **WebFetch tool** | Partially effective* |

*WebFetch fails for external URLs due to SSL certificate issues, but WebSearch works because it's processed by Anthropic's infrastructure as part of Claude's response generation.

### Attack Vectors

A compromised agent or prompt injection could:
1. **Encode data in search queries:** Private repo contents, API keys, business logic
2. **Exfiltrate via structured queries:** `WebSearch("company secret API key is AKIAIOSFODNN7EXAMPLE")`
3. **Access external resources indirectly:** Through Anthropic's search infrastructure

### Risk Assessment (from PR #686)

| Factor | Assessment |
|--------|------------|
| Likelihood | Low (requires prompt injection or agent compromise) |
| Impact | High (could leak private repo contents or secrets) |
| Detectability | Low (queries not visible in container logs) |
| Overall Risk | **Medium** |

---

## Problem Analysis

### Why This Is Difficult

1. **API-level processing:** WebSearch/WebFetch are processed by Anthropic's infrastructure, not by the local Claude Code client
2. **No local interception point:** The tools are invoked during Claude's response generation, not as separate network calls from the container
3. **Tool configuration is client-side:** Claude Code allows some tool restrictions via configuration, but comprehensive controls may not exist

### What We Need to Determine

1. **Can Claude Code disable specific tools?** Is there a configuration option to disable WebSearch/WebFetch?
2. **Does the Claude API support tool restrictions?** Can API calls specify which tools are available?
3. **Can we intercept at the proxy level?** Since requests go to `api.anthropic.com`, can we inspect/filter tool usage in the request payload?

---

## Investigation Results

### 1. Claude Code Configuration Options

**Finding:** Claude Code's settings include tool-related configuration, but comprehensive documentation on disabling specific built-in tools is limited.

**Known configuration areas:**
- MCP (Model Context Protocol) server configuration
- Custom tool definitions
- Tool approval prompts

**Unclear:**
- Whether built-in tools (WebSearch, WebFetch) can be disabled
- Whether there's an environment variable or config file option

### 2. Claude API Tool Controls

**Finding:** The Claude API supports tool use with explicit tool definitions. When tools are provided, Claude only uses those tools.

**Implication:** If we control the API call, we can control which tools are available. However, Claude Code manages API calls internally.

### 3. Proxy-Level Interception

**Finding:** The gateway proxy (Squid) performs SSL bump for `api.anthropic.com`. This means we CAN inspect and potentially modify API request payloads.

**Possibility:** Implement request filtering at the proxy level to:
- Remove WebSearch/WebFetch from tool definitions
- Block requests containing certain tool calls
- Audit tool usage in requests

---

## Implementation Options

### Option A: Claude Code Configuration (Preferred if Available)

**Description:** Configure Claude Code to disable WebSearch/WebFetch in private mode.

**Approach:**
1. Research Claude Code's tool configuration options
2. Set environment variable or config file option
3. Validate tools are disabled

**Pros:**
- Clean, supported approach
- No need for proxy-level inspection
- Easy to maintain

**Cons:**
- May not be possible if feature doesn't exist
- Requires Claude Code to support this configuration

**Implementation Effort:** Low (if supported)

### Option B: API Request Filtering at Proxy

**Description:** Filter Claude API requests at the gateway proxy to remove/block web tools.

**Approach:**
1. Configure Squid to inspect decrypted HTTPS traffic to `api.anthropic.com`
2. Implement a content filter (e.g., ICAP server or Squid helper)
3. Either:
   - Strip WebSearch/WebFetch from tool definitions in requests
   - Block requests that invoke these tools
   - Log tool usage for auditing

**Pros:**
- Works regardless of Claude Code configuration support
- Infrastructure-level control (security through infrastructure)
- Can audit all tool usage

**Cons:**
- Complex implementation (requires request parsing, modification)
- Performance overhead (content inspection)
- Fragile (depends on API request format)
- May break if Anthropic changes API format

**Implementation Effort:** High

### Option C: Container Environment Variable

**Description:** Set environment variable that Claude Code respects for tool restrictions.

**Approach:**
1. Research if Claude Code respects `DISABLE_WEB_SEARCH=true` or similar
2. Set in container environment
3. Validate behavior

**Pros:**
- Simple if supported
- Easy to toggle per-deployment

**Cons:**
- May not be supported
- Depends on Claude Code implementation

**Implementation Effort:** Low (if supported)

### Option D: Custom MCP Server Wrapper

**Description:** Wrap Claude Code to intercept and filter tool usage.

**Approach:**
1. Create MCP server that sits between Claude and actual tools
2. Filter out WebSearch/WebFetch in private mode
3. Route other tool calls through

**Pros:**
- Flexible, extensible
- Can add custom logic

**Cons:**
- Significant implementation effort
- Adds complexity to deployment
- May not intercept built-in tools (WebSearch/WebFetch are not MCP tools)

**Implementation Effort:** High

### Option E: Documentation Only (Short-term)

**Description:** Document the limitation and let operators decide.

**Approach:**
1. Add clear documentation about WebSearch/WebFetch in private mode
2. Explain the risk
3. Recommend use cases where this is acceptable

**Pros:**
- No implementation effort
- Transparent about limitations

**Cons:**
- Doesn't solve the security gap
- May not be acceptable for security-sensitive deployments

**Implementation Effort:** Minimal

---

## Recommended Approach

### Phase 1: Research (Immediate)

Before implementing any option, research Claude Code's actual capabilities:

1. **Check Claude Code documentation** for tool configuration options
2. **Inspect Claude Code's configuration files** for tool-related settings
3. **Test with environment variables** like `ANTHROPIC_DISABLE_WEB_SEARCH`
4. **Review Claude Code source** if available (it's open source)
5. **Contact Anthropic** if needed for API-level tool controls

### Phase 2: Implementation (Based on Research)

| If... | Then implement... |
|-------|-------------------|
| Claude Code supports tool disabling | Option A (Configuration) |
| No native support, but env var works | Option C (Environment Variable) |
| No client-side option available | Option B (Proxy Filtering) |
| Proxy filtering too complex for MVP | Option E (Documentation) with plan for Option B |

### Phase 3: Validation

Regardless of approach, validation should include:
1. Verify WebSearch returns error/is unavailable in private mode
2. Verify WebFetch returns error/is unavailable in private mode
3. Verify normal Claude operation is unaffected
4. Verify public mode still has full tool access (if desired)

---

## Research Tasks

To complete this pre-work, the following tasks are needed:

### Task 1: Claude Code Tool Configuration Research

**Description:** Investigate Claude Code's tool configuration options.

**Actions:**
1. Review Claude Code documentation at https://docs.anthropic.com/claude-code
2. Search for tool configuration in Claude Code repository
3. Check for `tools`, `disabled_tools`, or similar config options
4. Test environment variables in container

**Output:** List of available configuration options for tool control

### Task 2: API Request Format Analysis

**Description:** Understand Claude API request format for tool use.

**Actions:**
1. Capture sample API requests from Claude Code
2. Document tool definition format
3. Identify where WebSearch/WebFetch are specified
4. Determine if they're client-defined or server-side

**Output:** Documentation of API request format and tool handling

### Task 3: Prototype Proxy Filter (if needed)

**Description:** If client-side options aren't available, prototype proxy filtering.

**Actions:**
1. Configure Squid for request inspection
2. Create ICAP server or Squid helper
3. Implement tool filtering logic
4. Test with sample requests

**Output:** Working prototype or assessment that approach is infeasible

### Task 4: Implementation

**Description:** Implement chosen approach in jib before egg extraction.

**Actions:**
1. Implement tool controls
2. Add `DISABLE_WEB_TOOLS` or equivalent config option
3. Update documentation
4. Add tests

**Output:** Working implementation in james-in-a-box

---

## Blocking Status for Egg Extraction

This pre-work item is listed as a blocker in PR #693's Pre-Extraction Checklist:

```
- [ ] **Pre-work complete:** Claude tool access controls (WebSearch, WebFetch) implemented - see PR #686 security findings
```

### Recommendation

**The egg extraction should NOT be blocked on a complete solution.** Instead:

1. **For MVP (egg v1.0):** Implement documentation-only approach (Option E)
2. **For james-in-a-box:** Continue research and implement client-side controls if available
3. **Post-extraction:** If proxy filtering is needed, implement in egg as a feature

**Rationale:**
- The security gap exists in current jib and isn't new
- Egg extraction provides value independent of this issue
- The mitigation complexity shouldn't delay the extraction
- Documentation ensures operators are aware of the limitation

### Updated Pre-Work Requirement

Change from:
```
[ ] Pre-work complete: Claude tool access controls implemented
```

To:
```
[ ] Pre-work complete: Claude tool access controls documented with implementation plan
```

This allows extraction to proceed while tracking the implementation as a separate task.

---

## Next Steps

1. **Create beads task** for Claude tool access controls research
2. **Conduct research** per tasks above
3. **Update PR #693** with revised pre-work requirement
4. **Implement** based on research findings
5. **Document** limitation in egg security documentation

---

## Appendix A: Claude API Tool Use Format

Example Claude API request with tools (for reference):

```json
{
  "model": "claude-sonnet-4-20250514",
  "messages": [...],
  "tools": [
    {
      "name": "web_search",
      "description": "Search the web for information",
      "input_schema": {...}
    }
  ]
}
```

If tools are not specified, Claude uses no tools. If tools are specified, Claude only uses those tools.

**Key question:** Does Claude Code specify tools explicitly, or does the API enable certain tools by default based on the model/subscription?

---

## Appendix B: Related Documentation

- PR #686: Gateway sidecar security test documentation
- PR #693: Sandbox extraction proposal
- `docs/security/private-mode-pentest.md`: Full security testing results
- `egg-implementation-plan.md`: Pre-Work section

---

Authored-by: jib

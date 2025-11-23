# Pull Request Description Guidelines

When generating pull request descriptions, follow these guidelines to create concise yet informative summaries for reviewers.

## Format (Khan Academy Standard)

Use this template structure:

```
<one-line summary>

<full summary>

Issue: <JIRA link or "none">

Test plan:
<how this was tested>
```

## Guidelines for Each Section

### One-Line Summary
- **50 characters or less**
- Start with an imperative verb (Add, Fix, Update, Refactor, Remove)
- Be specific about what changed
- Examples:
  - ✅ "Add OAuth2 authentication to user service"
  - ✅ "Fix memory leak in conversation analyzer"
  - ❌ "Updates" (too vague)
  - ❌ "Implement feature requested by team" (not specific)

### Full Summary
- **2-3 paragraphs maximum**
- **Focus on WHAT and WHY, not HOW**
- Structure:
  1. **Context**: What problem does this solve? Why is it needed?
  2. **Changes**: What was changed at a high level?
  3. **Impact**: Who/what is affected? Any breaking changes?

- **Be concise**: Reviewers are busy. Get to the point.
- **Avoid implementation details**: Don't describe every function or variable
- **Link to related context**: Reference ADRs, Slack threads, docs if relevant

**Good example**:
```
This PR adds OAuth2 authentication to the user service to improve security
and enable SSO integration with corporate accounts.

The implementation follows ADR-042 (httpOnly cookies for auth tokens) and
integrates with our existing auth-service infrastructure. New endpoints
handle token refresh and validation.

This change affects all services that authenticate users. Existing session
tokens will continue to work during a 30-day migration period.
```

**Bad example**:
```
I added OAuth2 authentication by creating a new OAuthHandler class that
extends BaseHandler. The class has methods like handleTokenExchange() and
validateToken() that use the oauth2-library package. I also added a new
database table called oauth_tokens with columns for user_id, token, and
expiry. The config.py file now has new settings for OAuth2 client ID and
secret.
```

### Issue Link
- Link to JIRA ticket, GitHub issue, or Slack thread that motivated this work
- Use "none" if there's no formal issue tracking
- Examples:
  - `Issue: https://khanacademy.atlassian.net/browse/ENG-1234`
  - `Issue: https://khan-academy.slack.com/archives/C123/p1234567890`
  - `Issue: none`

### Test Plan
- **List specific steps reviewers should follow to verify the changes**
- Include commands to run (tests, builds, manual verification)
- Mention what to look for in the UI or logs
- Call out edge cases that were tested

**Good example**:
```
Test plan:
- Run `npm test` - all tests pass including 3 new OAuth2 tests
- Start dev server and navigate to /login - verify OAuth flow works
- Check that existing session tokens still work (backward compatibility)
- Verified token refresh works after 1 hour expiry
- Tested with invalid tokens - returns 401 as expected
```

**Bad example**:
```
Test plan:
- Tested it
- Works on my machine
```

## Special Considerations

### Draft PRs
- Mark as draft if:
  - Still in progress and not ready for full review
  - Seeking early feedback on approach
  - Blocked by another PR or dependency
- In description, clearly state:
  - What's complete and what's not
  - What feedback you're seeking
  - What blockers exist

### Breaking Changes
- **Clearly call out breaking changes in BOLD at the top of the summary**
- Explain migration path for affected code
- Example:
  ```
  **⚠️ BREAKING CHANGE**: This removes the deprecated `getUserData()` method.
  Migrate to `getUser()` instead.
  ```

### Large PRs
- If PR has >500 lines of changes, consider:
  - Breaking into smaller PRs if possible
  - Adding a "Reviewer Guide" section with suggested review order
  - Highlighting key files to focus on

## Length Guidelines

**Aim for conciseness**:
- One-line summary: ~50 chars
- Full summary: 200-400 words (2-3 paragraphs)
- Test plan: 3-7 bullet points
- **Total: Under 500 words**

If you find yourself writing more, you're probably including too many implementation details. Step back and focus on what reviewers need to know to evaluate the change.

## Anti-Patterns to Avoid

❌ **Too much detail**: "I changed line 42 to use forEach instead of map"
❌ **Vague**: "Updates to user service"
❌ **No context**: Jumping straight to changes without explaining why
❌ **Missing test plan**: Reviewers don't know how to verify
❌ **Implementation dump**: Listing every file and function changed
❌ **Novel-length**: 1000+ word descriptions
❌ **No issue link**: Missing context on why this work was prioritized

## Examples

### Excellent PR Description

```
Add rate limiting to API endpoints

Our API endpoints are vulnerable to abuse with no rate limiting. This PR
adds rate limiting middleware using the rate-limiter-flexible library,
following the approach in ADR-098.

All public API endpoints now have a default limit of 100 requests/minute per
IP. Admin endpoints have higher limits (500/min). Limits are configurable
via environment variables. Existing clients should not be affected as normal
usage is well below these limits.

Issue: https://khanacademy.atlassian.net/browse/SEC-456

Test plan:
- Run `npm test` - new rate limiting tests pass
- Start server and hit /api/users 105 times - see 429 after 100
- Verify rate limit headers are present (X-RateLimit-*)
- Check admin endpoints have higher limits
- Confirm rate limit resets after 1 minute
```

### Poor PR Description

```
Add rate limiting

I added rate limiting to the API because we need it. I used the
rate-limiter-flexible package and created a new middleware function called
rateLimiter() that checks the IP address against a Redis store. I also
added a new file called rateLimit.js with helper functions and updated
server.js to import the middleware. The config file now has settings for
rate limits.

Test plan:
- Tested it manually
```

## Summary

- **Be concise**: Respect reviewers' time
- **Focus on context**: Explain why, not how
- **Enable verification**: Clear test plan
- **Follow template**: One-line, summary, issue, test plan
- **Stay under 500 words total**

When in doubt, ask yourself: "What does the reviewer need to know to evaluate this change?" and write just that.

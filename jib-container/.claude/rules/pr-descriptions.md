# PR Description Guidelines

Concise, informative PR summaries for reviewers.

## Format (your organization Standard)

```
<one-line summary - 50 chars max>

<full summary - 2-3 paragraphs>

Issue: <JIRA link or "none">

Test plan:
<how this was tested>
```

## Guidelines

### One-Line Summary
- **50 characters or less**
- Start with imperative verb (Add, Fix, Update, Refactor, Remove)
- Be specific about what changed

### Full Summary
- **2-3 paragraphs maximum, focus on WHAT and WHY**
- Structure: Context → Changes → Impact
- Avoid implementation details (don't describe every function)
- Link to ADRs, Slack threads, docs if relevant

### Issue Link
- JIRA ticket, GitHub issue, or Slack thread
- Use "none" if no formal tracking

### Test Plan
- **Specific steps** reviewers can follow
- Include commands to run
- Mention what to look for
- Call out edge cases tested

## Special Considerations

**Breaking Changes**: Bold warning at top with migration path
```
**⚠️ BREAKING CHANGE**: Removes deprecated `getUserData()`.
Migrate to `getUser()` instead.
```

**Draft PRs**: State what's complete, what feedback you need, what blockers exist

**Large PRs (>500 lines)**: Consider splitting or add "Reviewer Guide" section

## Length Target

- One-line: ~50 chars
- Summary: 200-400 words
- Test plan: 3-7 bullets
- **Total: Under 500 words**

## Anti-Patterns

❌ Too much detail ("Changed line 42 to use forEach")
❌ Vague ("Updates to user service")
❌ No context (jumping to changes without why)
❌ Missing test plan
❌ Implementation dump (listing every file)
❌ Novel-length (1000+ words)

---
*Focus on what reviewers need to evaluate the change.*

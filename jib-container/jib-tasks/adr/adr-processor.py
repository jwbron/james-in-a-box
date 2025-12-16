#!/usr/bin/env python3
"""
ADR Processor - Container-side dispatcher for ADR research tasks.

This script is invoked by the host-side adr-researcher.py via `jib --exec`.
It receives context via command-line arguments and dispatches to the
appropriate handler based on task type.

Usage:
    jib --exec python3 adr-processor.py --task <task_type> --context <json>

Task types:
    - research_adr: Research an existing ADR's topics and output findings
    - generate_adr: Generate a new ADR from research on a topic
    - review_adr: Review and validate an ADR against current research
    - research_topic: Research a specific topic (general query)

Per ADR-LLM-Documentation-Index-Strategy Phase 6:
    - Host-side adr-researcher identifies ADRs and triggers container
    - Container performs web research via Claude and outputs findings
    - Results are posted as PR comments or used to create update PRs
"""

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path


# Import shared modules
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))
from llm import run_agent


def utc_now_iso() -> str:
    """Get current UTC time in ISO format."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def handle_research_adr(context: dict) -> dict:
    """Research an existing ADR and output findings.

    Context expected:
        - adr_title: str
        - adr_content: str (first ~20k chars)
        - topics: list[str]
        - pr_number: int | None (if open PR exists)
        - pr_url: str | None
        - output_mode: "pr_comment" | "update_pr" | "report"
    """
    adr_title = context.get("adr_title", "Untitled ADR")
    topics = context.get("topics", [])
    pr_number = context.get("pr_number")
    output_mode = context.get("output_mode", "report")

    print(f"Researching ADR: {adr_title}")
    print(f"  Topics: {', '.join(topics)}")
    print(f"  Output mode: {output_mode}")

    prompt = build_research_prompt(context)

    # Run Claude for research
    print("Invoking Claude for research...")
    result = run_agent(prompt, cwd=Path.home() / "khan")

    if result.success:
        print("Claude research completed successfully")
        return {
            "success": True,
            "adr_title": adr_title,
            "pr_number": pr_number,
            "output_mode": output_mode,
            "output": result.stdout[:5000] if result.stdout else "",
        }
    else:
        print(f"Research failed: {result.error}")
        return {
            "success": False,
            "error": result.error,
            "stderr": result.stderr[:1000] if result.stderr else "",
        }


def build_research_prompt(context: dict) -> str:
    """Build the prompt for Claude to research an ADR."""
    adr_title = context.get("adr_title", "Untitled ADR")
    adr_content = context.get("adr_content", "")
    topics = context.get("topics", [])
    adr_path = context.get("adr_path", "")
    pr_number = context.get("pr_number")
    pr_url = context.get("pr_url")
    output_mode = context.get("output_mode", "report")
    prior_research = context.get("prior_research", "")
    prior_pr_numbers = context.get("prior_pr_numbers", [])

    # Extract key sections from ADR for focused research
    adr_excerpt = adr_content[:15000] if adr_content else "No content available"

    prompt = f"""# ADR Research Task

## ADR Information
- **Title**: {adr_title}
- **Path**: {adr_path or "Not specified"}
- **Topics**: {", ".join(topics) if topics else "General"}
{f"- **PR**: #{pr_number} ({pr_url})" if pr_number else ""}

## ADR Content (Excerpt)
```markdown
{adr_excerpt}
```

{
        f'''## Prior Research to Integrate

**IMPORTANT:** There are {len(prior_pr_numbers)} prior research PR(s) for this ADR that will be closed when this new research is created: {", ".join(f"#{n}" for n in prior_pr_numbers)}

You MUST integrate the relevant findings from the prior research below into your new research. Update findings that are still valid, and note which prior findings have been superseded by newer information.

{prior_research}

When creating the new PR:
1. Reference that this PR supersedes the prior research PRs
2. Preserve valuable findings from prior research where still relevant
3. Note any findings that have been updated or superseded

'''
        if prior_research
        else ""
    }
## Research Instructions

You are tasked with researching current industry best practices and trends related to this ADR.

### Step 1: Identify Research Questions

Based on the ADR content, identify 3-5 key research questions:
- What are current best practices for the technologies/patterns discussed?
- Have industry standards changed since this ADR was written?
- What are common pitfalls or anti-patterns to avoid?
- What do official documentation sources recommend?
- Are there newer/better approaches available?

### Step 2: Conduct Web Research

Use web search to find current information on:
1. Official documentation for mentioned technologies
2. Recent blog posts from framework authors or industry experts
3. Academic papers or standards (OWASP, NIST, etc.) if security-related
4. Popular open-source projects using similar patterns
5. Recent conference talks or announcements

Focus on sources from 2024-2025 for the most current information.

### Step 3: Synthesize Findings

Create a "Research Updates" section following this format:

```markdown
## Research Updates ({datetime.now().strftime("%B %Y")})

Based on external research into [topic]:

### [Subtopic 1]

[Key findings with context]

| Aspect | Current State | Industry Trend |
|--------|---------------|----------------|
| ...    | ...           | ...            |

**Application to this ADR:**
- Specific recommendation 1
- Specific recommendation 2

### [Subtopic 2]

[Additional findings...]

### Research Sources

- [Source Title](URL) - Brief description of relevance
- [Source Title](URL) - Brief description of relevance
```

### Step 4: Output Results

"""

    if output_mode == "pr_comment":
        prompt += f"""Post your findings as a comment on PR #{pr_number}:

```bash
gh pr comment {pr_number} --body "$(cat <<'EOF'
## 🔍 Research-Based ADR Review

**Reviewed:** {adr_title}
**Research Date:** {utc_now_iso()}

[Your research findings here following the template above]

---
*— Research by jib*
EOF
)"
```
"""
    elif output_mode == "update_pr":
        supersedes_note = ""
        if prior_pr_numbers:
            supersedes_note = f"""
   - In the PR body, add a "Supersedes" section listing: {", ".join(f"#{n}" for n in prior_pr_numbers)}
   - Note which findings from prior PRs are integrated vs updated vs superseded"""

        prompt += f"""Create a PR with your research findings:

1. Create a new branch from main
2. Update the ADR file at `{adr_path}` by appending your "Research Updates" section before the "## References" section (or at the end if no References section exists)
3. Commit with message: "Add research updates to {adr_title}"
4. Create a PR with:
   - Title: "Research updates for {adr_title}"
   - Body explaining what was researched and key findings{supersedes_note}
5. Output the PR URL at the end of your response as: `PR_URL: <url>`
"""
    else:  # report mode
        prompt += """Output your research findings in markdown format directly.
Start with the "## Research Updates" section and include all findings.
"""

    prompt += """
## Important Guidelines

- **Be specific**: Include concrete examples and citations
- **Be current**: Prioritize recent sources (2024-2025)
- **Be actionable**: Provide specific recommendations for this codebase
- **Be honest**: If you can't find relevant research, say so
- **Cite sources**: Always include URLs to the sources you found

Begin research now.
"""

    return prompt


def handle_generate_adr(context: dict) -> dict:
    """Generate a new ADR from research on a topic.

    Context expected:
        - topic: str
        - output_dir: str (e.g., "docs/adr/not-implemented")
        - output_mode: "new_pr" | "report"
    """
    topic = context.get("topic", "Unknown Topic")
    output_dir = context.get("output_dir", "docs/adr/not-implemented")
    output_mode = context.get("output_mode", "new_pr")

    print(f"Generating ADR for topic: {topic}")
    print(f"  Output dir: {output_dir}")
    print(f"  Output mode: {output_mode}")

    prompt = build_generate_prompt(context)

    # Run Claude for generation
    print("Invoking Claude for ADR generation...")
    result = run_agent(prompt, cwd=Path.home() / "khan" / "james-in-a-box")

    if result.success:
        print("Claude ADR generation completed successfully")
        # Try to extract PR URL from output
        pr_url = None
        if result.stdout:
            for line in result.stdout.split("\n"):
                if "PR_URL:" in line:
                    pr_url = line.split("PR_URL:")[-1].strip()
                    break

        return {
            "success": True,
            "topic": topic,
            "pr_url": pr_url,
            "output": result.stdout[:5000] if result.stdout else "",
        }
    else:
        print(f"Generation failed: {result.error}")
        return {
            "success": False,
            "error": result.error,
            "stderr": result.stderr[:1000] if result.stderr else "",
        }


def build_generate_prompt(context: dict) -> str:
    """Build the prompt for Claude to generate a new ADR."""
    topic = context.get("topic", "Unknown Topic")
    output_dir = context.get("output_dir", "docs/adr/not-implemented")
    output_mode = context.get("output_mode", "new_pr")

    # Convert topic to filename-safe format
    safe_topic = topic.replace(" ", "-").replace("/", "-")
    safe_topic = "".join(c for c in safe_topic if c.isalnum() or c == "-")
    adr_filename = f"ADR-{safe_topic}.md"

    prompt = f"""# ADR Generation Task

## Topic
{topic}

## Output
- **Directory**: {output_dir}
- **Filename**: {adr_filename}

## Instructions

You are tasked with generating a complete ADR (Architecture Decision Record) for the topic "{topic}".

### Step 1: Research the Topic

Before writing the ADR, conduct web research to understand:
1. Current industry best practices related to this topic
2. Common approaches and their trade-offs
3. What leading companies/projects are doing
4. Potential pitfalls and anti-patterns
5. Recent developments or trends (2024-2025)

### Step 2: Generate the ADR

Create a complete ADR following this template:

```markdown
# ADR: {topic}

**Driver:** jib (AI-generated, requires human approval)
**Approver:** TBD
**Contributors:** jib
**Informed:** Engineering teams
**Proposed:** {datetime.now().strftime("%B %Y")}
**Status:** Proposed

## Table of Contents

[Auto-generate based on sections]

## Context

### Background

[Research-derived context about the problem space - what problem are we solving?]

### Industry Landscape

[Summary of current industry practices with citations]

| Approach | Adoption | Key Trade-offs |
|----------|----------|----------------|
| ...      | ...      | ...            |

### What We're Deciding

[Specific decision to be made]

### Key Requirements

[List requirements that must be met]

## Decision

[Recommended approach with research justification]

## Decision Matrix

| Criterion | Option A | Option B | Option C |
|-----------|----------|----------|----------|
| ...       | ...      | ...      | ...      |

*Evaluation criteria derived from [source citations]*

## Implementation Details

[How the decision would be implemented]

## Consequences

### Benefits
- [List benefits]

### Drawbacks
- [List drawbacks]

### Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| ...  | ...        |

## Alternatives Considered

### Alternative 1: [Name]
**Research findings:** [What external sources say]
**Rejected because:** [Research-backed reasoning]

### Alternative 2: [Name]
...

## References

- [Source Title](URL) - How it informed the decision
- [Source Title](URL) - How it informed the decision
```

### Step 3: Create the ADR File

"""

    if output_mode == "new_pr":
        prompt += f"""1. Create a new branch from main:
   ```bash
   git checkout -b adr/{safe_topic.lower()} origin/main
   ```

2. Write the ADR to `{output_dir}/{adr_filename}`

3. Commit with a clear message:
   ```bash
   git add {output_dir}/{adr_filename}
   git commit -m "Add ADR: {topic}

   Generate ADR for {topic} based on web research.

   🤖 Generated with Claude Code"
   ```

4. Push and create PR:
   ```bash
   git push origin adr/{safe_topic.lower()}
   gh pr create --title "ADR: {topic}" --body "$(cat <<'EOF'
## Summary

Proposes an ADR for {topic} based on current industry research.

## Key Points

[Summarize the key decision and alternatives]

## Research Sources

[List main sources consulted]

## Test plan

- [ ] ADR follows template format
- [ ] Research sources are valid and current
- [ ] Alternatives are fairly evaluated

🤖 Generated with Claude Code
EOF
)"
   ```

5. Output the PR URL at the end: `PR_URL: <url>`
"""
    else:  # report mode
        prompt += f"""Output the complete ADR in markdown format directly.
The ADR should be ready to save to `{output_dir}/{adr_filename}`.
"""

    prompt += """
## Important Guidelines

- **Ground in research**: Every major claim should have supporting evidence
- **Be balanced**: Present alternatives fairly, even if recommending one
- **Be specific**: Include concrete examples, not vague generalizations
- **Cite sources**: Always include URLs for research findings
- **Follow template**: Use the exact template structure provided

Begin research and generation now.
"""

    return prompt


def handle_review_adr(context: dict) -> dict:
    """Review and validate an ADR against current research.

    Context expected:
        - adr_title: str
        - adr_path: str
        - adr_content: str
        - topics: list[str]
        - pr_number: int | None
        - pr_url: str | None
        - output_mode: "pr_comment" | "report"
    """
    adr_title = context.get("adr_title", "Untitled ADR")
    adr_path = context.get("adr_path", "")
    pr_number = context.get("pr_number")
    output_mode = context.get("output_mode", "report")

    print(f"Reviewing ADR: {adr_title}")
    print(f"  Path: {adr_path}")
    print(f"  Output mode: {output_mode}")

    prompt = build_review_prompt(context)

    # Run Claude for review
    print("Invoking Claude for ADR review...")
    result = run_agent(prompt, cwd=Path.home() / "khan" / "james-in-a-box")

    if result.success:
        print("Claude ADR review completed successfully")
        return {
            "success": True,
            "adr_title": adr_title,
            "pr_number": pr_number,
            "output_mode": output_mode,
            "output": result.stdout[:5000] if result.stdout else "",
        }
    else:
        print(f"Review failed: {result.error}")
        return {
            "success": False,
            "error": result.error,
            "stderr": result.stderr[:1000] if result.stderr else "",
        }


def build_review_prompt(context: dict) -> str:
    """Build the prompt for Claude to review an ADR."""
    adr_title = context.get("adr_title", "Untitled ADR")
    adr_content = context.get("adr_content", "")
    adr_path = context.get("adr_path", "")
    topics = context.get("topics", [])
    pr_number = context.get("pr_number")
    pr_url = context.get("pr_url")
    output_mode = context.get("output_mode", "report")

    adr_excerpt = adr_content[:15000] if adr_content else "No content available"

    prompt = f"""# ADR Review Task

## ADR Information
- **Title**: {adr_title}
- **Path**: {adr_path}
- **Topics**: {", ".join(topics) if topics else "General"}
{f"- **PR**: #{pr_number} ({pr_url})" if pr_number else ""}

## ADR Content
```markdown
{adr_excerpt}
```

## Review Instructions

You are tasked with validating this ADR against current industry research.

### Step 1: Parse the ADR

Extract from the ADR:
1. Core decision and alternatives discussed
2. Claims made about technologies or approaches
3. Trade-off assertions
4. Referenced sources (if any)

### Step 2: Validate Each Claim

For each significant claim or assertion in the ADR:
1. Research whether the claim is accurate based on current sources
2. Check if the sources cited (if any) are still valid
3. Identify if there are newer developments that contradict the claim
4. Note any alternatives that weren't mentioned

### Step 3: Produce Review Output

Create a review comment following this format:

```markdown
## 🔍 Research-Based ADR Review

**Reviewed:** {adr_title}
**Research Date:** {utc_now_iso()}

### ✅ Validated Claims

- **Claim:** "[Quoted claim from ADR]"
  - **Validation:** [Supporting research]
  - **Source:** [URL]

### ⚠️ Needs Update

- **Claim:** "[Outdated claim]"
  - **Current Status:** [What research shows now]
  - **Suggested Update:** [Recommended revision]
  - **Source:** [URL]

### ❌ Potentially Incorrect

- **Claim:** "[Questionable assertion]"
  - **Research Contradicts:** [What sources actually say]
  - **Recommendation:** [How to address]
  - **Source:** [URL]

### 💡 Additional Considerations

- [Alternative or pattern not mentioned in ADR]
  - **Relevance:** [Why reviewer should consider]
  - **Source:** [URL]

### 📚 Supplementary Sources

- [Source](URL) - Brief description
- [Source](URL) - Brief description

---
*— Research review by jib*
```

### Step 4: Output Results

"""

    if output_mode == "pr_comment" and pr_number:
        prompt += f"""Post your review as a comment on PR #{pr_number}:

```bash
gh pr comment {pr_number} --body "$(cat <<'EOF'
[Your review content here]
EOF
)"
```
"""
    else:  # report mode
        prompt += """Output your review findings in markdown format directly.
"""

    prompt += """
## Important Guidelines

- **Be constructive**: Focus on helping improve the ADR, not criticizing
- **Be specific**: Quote exact claims and provide exact sources
- **Be fair**: Acknowledge what the ADR gets right
- **Be current**: Use 2024-2025 sources when possible
- **Be honest**: If you can't verify something, say so

Begin review now.
"""

    return prompt


def handle_research_topic(context: dict) -> dict:
    """Research a specific topic (general query).

    Context expected:
        - query: str
        - output_mode: "pr" | "report"
    """
    query = context.get("query", "")
    output_mode = context.get("output_mode", "report")

    print(f"Researching topic: {query}")
    print(f"  Output mode: {output_mode}")

    prompt = f"""# Topic Research Task

## Query
{query}

## Instructions

Research the topic "{query}" and provide comprehensive findings.

### Research Areas

1. Current best practices (2024-2025)
2. Common approaches and trade-offs
3. Industry adoption and trends
4. Potential pitfalls and anti-patterns
5. Authoritative sources and documentation

### Output Format

Provide your findings in this format:

```markdown
# Research: {query}

**Research Date:** {utc_now_iso()}

## Summary

[2-3 sentence overview of findings]

## Key Findings

### [Finding 1]
[Details with citations]

### [Finding 2]
[Details with citations]

## Industry Adoption

| Organization/Project | Approach | Notes |
|---------------------|----------|-------|
| ...                 | ...      | ...   |

## Best Practices

1. [Practice 1] - [Why]
2. [Practice 2] - [Why]

## Anti-Patterns to Avoid

1. [Anti-pattern 1] - [Why]
2. [Anti-pattern 2] - [Why]

## Recommendations

For james-in-a-box specifically:
- [Recommendation 1]
- [Recommendation 2]

## Sources

- [Source Title](URL) - Description
- [Source Title](URL) - Description

---
*— Research by jib*
```

Begin research now.
"""

    # Run Claude for research
    print("Invoking Claude for topic research...")
    result = run_agent(prompt, cwd=Path.home() / "khan")

    if result.success:
        print("Claude topic research completed successfully")
        return {
            "success": True,
            "query": query,
            "output": result.stdout if result.stdout else "",
        }
    else:
        print(f"Research failed: {result.error}")
        return {
            "success": False,
            "error": result.error,
            "stderr": result.stderr[:1000] if result.stderr else "",
        }


def main():
    """Main entry point - parse arguments and dispatch to handler."""
    parser = argparse.ArgumentParser(
        description="ADR Processor - Container-side task dispatcher for ADR research"
    )
    parser.add_argument(
        "--task",
        required=True,
        choices=["research_adr", "generate_adr", "review_adr", "research_topic"],
        help="Type of task to process",
    )
    parser.add_argument(
        "--context",
        required=True,
        help="JSON context for the task",
    )

    args = parser.parse_args()

    # Parse context
    try:
        context = json.loads(args.context)
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON context: {e}")
        result = {"success": False, "error": f"Invalid JSON: {e}"}
        print(json.dumps(result))
        sys.exit(1)

    print("=" * 60)
    print(f"ADR Processor - {args.task}")
    print(f"Time: {utc_now_iso()}")
    print("=" * 60)

    # Dispatch to appropriate handler
    handlers = {
        "research_adr": handle_research_adr,
        "generate_adr": handle_generate_adr,
        "review_adr": handle_review_adr,
        "research_topic": handle_research_topic,
    }

    handler = handlers.get(args.task)
    if handler:
        result = handler(context)
    else:
        result = {"success": False, "error": f"Unknown task type: {args.task}"}

    print("=" * 60)
    print("ADR Processor - Completed")
    print("=" * 60)

    # Output result as JSON for host to parse
    print(json.dumps(result))


if __name__ == "__main__":
    main()

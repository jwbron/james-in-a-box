#!/usr/bin/env python3
"""
Confluence Watcher - Monitors Confluence documentation changes

Detects new or updated Confluence documents (especially ADRs), summarizes
changes, identifies impact on current work, and sends notifications.

Uses Claude Code to intelligently analyze documentation and identify impacts.

Focus: ADRs, runbooks, and engineering documentation
"""

import json
import sys
from datetime import datetime
from pathlib import Path


# Import shared Claude runner
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))
from claude import run_claude


def main():
    """Run one-shot Confluence documentation analysis using Claude Code."""
    print("🔍 Confluence Watcher - Analyzing documentation changes...")

    confluence_dir = Path.home() / "context-sync" / "confluence"
    state_file = Path.home() / "sharing" / "tracking" / "confluence-watcher-state.json"

    if not confluence_dir.exists():
        print("Confluence directory not found - skipping watch")
        return 0

    # Load state to track processed documents
    processed_docs = {}
    if state_file.exists():
        try:
            with state_file.open() as f:
                data = json.load(f)
                processed_docs = data.get("processed", {})
        except (OSError, json.JSONDecodeError) as e:
            print(f"Warning: Failed to load state: {e}")

    # Focus on high-value documents: ADRs and Runbooks
    adr_files = list(confluence_dir.rglob("*ADR*.md")) + list(confluence_dir.rglob("*adr*.md"))
    runbook_files = list(confluence_dir.rglob("*unbook*.md")) + list(
        confluence_dir.rglob("*RUNBOOK*.md")
    )

    # Collect new or updated documents
    new_or_updated = []

    # Process ADRs first (highest priority)
    for doc_file in adr_files[:10]:  # Limit to avoid spam
        try:
            mtime = doc_file.stat().st_mtime
            mtime_str = datetime.fromtimestamp(mtime).isoformat()
            doc_path = str(doc_file)

            # Check if new or updated
            if doc_path not in processed_docs or processed_docs[doc_path] != mtime_str:
                content = doc_file.read_text()
                is_new = doc_path not in processed_docs

                new_or_updated.append(
                    {
                        "file": doc_file,
                        "path": doc_path,
                        "mtime": mtime_str,
                        "is_new": is_new,
                        "doc_type": "ADR",
                        "content": content,
                    }
                )
        except Exception as e:
            print(f"Error processing {doc_file}: {e}")

    # Then runbooks
    for doc_file in runbook_files[:5]:
        try:
            mtime = doc_file.stat().st_mtime
            mtime_str = datetime.fromtimestamp(mtime).isoformat()
            doc_path = str(doc_file)

            # Check if new or updated
            if doc_path not in processed_docs or processed_docs[doc_path] != mtime_str:
                content = doc_file.read_text()
                is_new = doc_path not in processed_docs

                new_or_updated.append(
                    {
                        "file": doc_file,
                        "path": doc_path,
                        "mtime": mtime_str,
                        "is_new": is_new,
                        "doc_type": "Runbook",
                        "content": content,
                    }
                )
        except Exception as e:
            print(f"Error processing {doc_file}: {e}")

    if not new_or_updated:
        print("No new or updated documentation found")
        return 0

    print(f"Found {len(new_or_updated)} new or updated document(s)")

    # Construct prompt for Claude
    docs_summary = []
    for d in new_or_updated:
        status = "New" if d["is_new"] else "Updated"
        docs_summary.append(f"**{status} {d['doc_type']}**: {d['file'].name}")

    prompt = f"""# Confluence Documentation Analysis

You are analyzing Confluence documentation that has been created or updated. Your goal is to understand architectural decisions, identify impacts on current work, and extract actionable insights.

## Summary

{len(new_or_updated)} document(s) require attention:
{chr(10).join("- " + s for s in docs_summary)}

## Full Document Details

"""

    for d in new_or_updated:
        status = "NEW" if d["is_new"] else "UPDATED"
        prompt += f"""
### {status} {d["doc_type"]}: {d["file"].name}

**Type:** {d["doc_type"]}
**File:** `{d["file"]}`

**Content:**
```markdown
{d["content"][:3000]}{"..." if len(d["content"]) > 3000 else ""}
```

---

"""

    prompt += """
## Your Workflow (per ADR)

For each document:

1. **Analyze the document**:
   - Understand the main purpose and key decisions
   - For ADRs: Identify architectural decisions, patterns, standards
   - For Runbooks: Identify processes, procedures, operational guidance
   - Extract key technologies or tools mentioned
   - Identify deprecations, migrations, or breaking changes
   - Assess impact on current or future work
   - Look for action items or required changes

2. **Track in Beads** (for ADRs only):
   - Create Beads task: `bd --allow-stale create "Review ADR: <title>" --labels adr,confluence,documentation`
   - Add notes with: document title, file name, related technologies
   - Only for NEW ADRs (not updates)

3. **Create notification** to `~/sharing/notifications/`:
   - Use format: `YYYYMMDD-HHMMSS-confluence-{new|updated}-<doc-name>.md`
   - Include:
     - Document title and type (ADR/Runbook/etc)
     - File path
     - Beads task ID if created
     - Summary of document purpose
     - Impact assessment (how does this affect current/future work?)
     - Key points or decisions
     - Related technologies mentioned
     - Important changes (deprecations, migrations, action items)
     - Suggested next steps for the user
   - Keep it concise but informative

4. **Update state file**:
   - Save document path and mtime to `~/sharing/tracking/confluence-watcher-state.json`
   - This prevents re-processing unchanged documents

## Important Notes

- You're in an ephemeral container
- Documents are synced to ~/context-sync/confluence/
- Focus on high-value docs: ADRs and Runbooks
- ADRs may affect implementation approaches - highlight impacts
- Use Beads to track ADR reviews across sessions
- Notifications will be sent to Slack automatically

Analyze these documents now and take appropriate action."""

    # Run Claude Code
    result = run_claude(prompt, timeout=900, capture_output=False)

    if result.success:
        print("✅ Documentation analysis complete")

        # Update state file with processed documents
        for d in new_or_updated:
            processed_docs[d["path"]] = d["mtime"]

        state_file.parent.mkdir(parents=True, exist_ok=True)
        with state_file.open("w") as f:
            json.dump({"processed": processed_docs}, f, indent=2)

        return 0
    else:
        print(f"⚠️ {result.error}")
        return 1


if __name__ == "__main__":
    sys.exit(main())

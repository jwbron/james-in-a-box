"""
JIRA sync script.

Syncs JIRA tickets and their comments to local markdown files.
"""

import base64
import hashlib
import pickle
import re
import sys
from pathlib import Path

import requests


# Add shared directory to path for jib_logging
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent.parent / "shared"))
from jib_logging import get_logger

from connectors.jira.config import JIRAConfig


# Initialize logger
logger = get_logger("jira-sync")


class JIRASync:
    """Sync JIRA tickets to local files."""

    def __init__(self):
        self.config = JIRAConfig()
        self.session = requests.Session()
        self._setup_auth()
        self.sync_state_file = Path(self.config.OUTPUT_DIR) / ".sync_state"

    def _setup_auth(self):
        """Setup authentication for JIRA API."""
        if not self.config.validate():
            raise ValueError(
                "Missing required configuration. Please set JIRA_BASE_URL, "
                "JIRA_USERNAME, and JIRA_API_TOKEN"
            )

        # Use Basic auth with email:token for Atlassian Cloud
        auth_string = f"{self.config.USERNAME}:{self.config.API_TOKEN}"
        auth_bytes = auth_string.encode("ascii")
        auth_b64 = base64.b64encode(auth_bytes).decode("ascii")

        self.session.headers.update(
            {
                "Authorization": f"Basic {auth_b64}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
        )

    def _load_sync_state(self) -> dict:
        """Load sync state from file."""
        if self.sync_state_file.exists():
            try:
                with open(self.sync_state_file, "rb") as f:
                    state = pickle.load(f)
                    logger.debug(
                        "Loaded sync state",
                        state_file=str(self.sync_state_file),
                        issue_count=len(state),
                    )
                    return state
            except Exception as e:
                logger.error(
                    "Failed to load sync state",
                    state_file=str(self.sync_state_file),
                    error=str(e),
                    error_type=type(e).__name__,
                )
        else:
            logger.debug("No existing sync state file found", state_file=str(self.sync_state_file))
        return {}

    def _save_sync_state(self, state: dict):
        """Save sync state to file."""
        self.sync_state_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.sync_state_file, "wb") as f:
            pickle.dump(state, f)

    def _get_ticket_hash(self, issue: dict) -> str:
        """Generate hash for ticket to detect changes."""
        # Include updated timestamp and comment count
        issue_key = issue.get("key", "")
        updated = issue.get("fields", {}).get("updated", "")
        comment_count = issue.get("fields", {}).get("comment", {}).get("total", 0)

        content = f"{issue_key}_{updated}_{comment_count}"
        return hashlib.md5(content.encode()).hexdigest()

    def _sanitize_filename(self, filename: str) -> str:
        """Sanitize filename for filesystem."""
        # Remove problematic characters
        filename = re.sub(r'[<>:"/\\|?*]', "_", filename)
        filename = re.sub(r"[\x00-\x1f\x7f]", "", filename)
        filename = filename.strip()
        return filename[:200]

    def search_issues(self, jql: str | None = None) -> list[dict]:
        """Search for issues using JQL."""
        if jql is None:
            jql = self.config.JQL_QUERY

        issues = []
        start_at = 0
        max_results = 50
        api_calls = 0

        logger.info("Searching JIRA issues", jql=jql[:100] if len(jql) > 100 else jql)

        while True:
            url = f"{self.config.BASE_URL}/rest/api/3/search/jql"
            params = {
                "jql": jql,
                "startAt": start_at,
                "maxResults": max_results,
                "fields": "summary,description,status,assignee,reporter,created,updated,priority,labels,components,issuetype,comment,attachment,worklog",
            }

            try:
                response = self.session.get(url, params=params, timeout=self.config.REQUEST_TIMEOUT)
                response.raise_for_status()

                data = response.json()
                new_issues = data.get("issues", [])
                issues.extend(new_issues)
                api_calls += 1

                logger.debug(
                    "Fetched issue batch",
                    batch_size=len(new_issues),
                    total_issues=len(issues),
                    api_calls=api_calls,
                )

                # Check if we have more results
                total = data.get("total", 0)
                if start_at + max_results >= total:
                    break

                # Check if we've hit our limit
                if (
                    float("inf") != self.config.MAX_TICKETS
                    and len(issues) >= self.config.MAX_TICKETS
                ):
                    logger.info("Reached issue limit", limit=self.config.MAX_TICKETS)
                    break

                start_at += max_results

            except requests.exceptions.RequestException as e:
                logger.error(
                    "Error searching issues",
                    error=str(e),
                    error_type=type(e).__name__,
                )
                break

        logger.info(
            "Issue search completed",
            total_issues=len(issues),
            api_calls=api_calls,
        )
        if float("inf") != self.config.MAX_TICKETS:
            return issues[: int(self.config.MAX_TICKETS)]
        return issues

    def format_issue_as_markdown(self, issue: dict) -> str:
        """Format a JIRA issue as markdown."""
        fields = issue.get("fields", {})
        issue_key = issue.get("key", "")

        # Build markdown content
        lines = []
        lines.append(f"# {issue_key}: {fields.get('summary', 'No title')}")
        lines.append("")

        # Metadata
        issue_url = f"{self.config.BASE_URL}/browse/{issue_key}"
        lines.append(f"**URL:** [{issue_key}]({issue_url})")
        lines.append(f"**Type:** {fields.get('issuetype', {}).get('name', 'Unknown')}")
        lines.append(f"**Status:** {fields.get('status', {}).get('name', 'Unknown')}")
        lines.append(f"**Priority:** {fields.get('priority', {}).get('name', 'Unknown')}")

        # People
        assignee = fields.get("assignee")
        if assignee:
            lines.append(f"**Assignee:** {assignee.get('displayName', 'Unknown')}")

        reporter = fields.get("reporter")
        if reporter:
            lines.append(f"**Reporter:** {reporter.get('displayName', 'Unknown')}")

        # Dates
        created = fields.get("created", "")
        if created:
            lines.append(f"**Created:** {created}")

        updated = fields.get("updated", "")
        if updated:
            lines.append(f"**Updated:** {updated}")

        # Labels
        labels = fields.get("labels", [])
        if labels:
            lines.append(f"**Labels:** {', '.join(labels)}")

        # Components
        components = fields.get("components", [])
        if components:
            comp_names = [c.get("name", "") for c in components]
            lines.append(f"**Components:** {', '.join(comp_names)}")

        lines.append("")
        lines.append("---")
        lines.append("")

        # Description
        lines.append("## Description")
        lines.append("")
        description = fields.get("description")
        if description:
            # JIRA API v3 uses Atlassian Document Format
            lines.append(self._format_adf_content(description))
        else:
            lines.append("*No description*")
        lines.append("")

        # Comments
        if self.config.INCLUDE_COMMENTS:
            comments = fields.get("comment", {}).get("comments", [])
            if comments:
                lines.append("## Comments")
                lines.append("")
                for idx, comment in enumerate(comments, 1):
                    author = comment.get("author", {}).get("displayName", "Unknown")
                    created = comment.get("created", "")
                    lines.append(f"### Comment {idx} - {author} ({created})")
                    lines.append("")
                    body = comment.get("body")
                    if body:
                        lines.append(self._format_adf_content(body))
                    lines.append("")

        # Attachments
        if self.config.INCLUDE_ATTACHMENTS:
            attachments = fields.get("attachment", [])
            if attachments:
                lines.append("## Attachments")
                lines.append("")
                for att in attachments:
                    filename = att.get("filename", "Unknown")
                    size = att.get("size", 0)
                    created = att.get("created", "")
                    author = att.get("author", {}).get("displayName", "Unknown")
                    content_url = att.get("content", "")
                    lines.append(
                        f"- **{filename}** ({size} bytes) - uploaded by {author} on {created}"
                    )
                    if content_url:
                        lines.append(f"  - [Download]({content_url})")
                lines.append("")

        # Work logs
        if self.config.INCLUDE_WORKLOGS:
            worklogs = fields.get("worklog", {}).get("worklogs", [])
            if worklogs:
                lines.append("## Work Logs")
                lines.append("")
                for log in worklogs:
                    author = log.get("author", {}).get("displayName", "Unknown")
                    started = log.get("started", "")
                    time_spent = log.get("timeSpent", "")
                    comment = log.get("comment", "")
                    lines.append(f"- **{author}** - {time_spent} on {started}")
                    if comment:
                        lines.append(f"  - {comment}")
                lines.append("")

        return "\n".join(lines)

    def _format_adf_content(self, adf: dict) -> str:
        """Format Atlassian Document Format (ADF) content to markdown."""
        if not isinstance(adf, dict):
            return str(adf)

        if adf.get("type") == "doc":
            # Process document content
            content_parts = []
            for node in adf.get("content", []):
                content_parts.append(self._format_adf_node(node))
            return "\n\n".join(content_parts)

        return str(adf)

    def _format_adf_node(self, node: dict) -> str:
        """Format a single ADF node to markdown."""
        node_type = node.get("type", "")

        if node_type == "paragraph":
            content_parts = []
            for item in node.get("content", []):
                content_parts.append(self._format_adf_node(item))
            return "".join(content_parts)

        elif node_type == "text":
            text = node.get("text", "")
            # Apply marks (bold, italic, etc.)
            for mark in node.get("marks", []):
                mark_type = mark.get("type")
                if mark_type == "strong":
                    text = f"**{text}**"
                elif mark_type == "em":
                    text = f"*{text}*"
                elif mark_type == "code":
                    text = f"`{text}`"
                elif mark_type == "link":
                    href = mark.get("attrs", {}).get("href", "")
                    text = f"[{text}]({href})"
            return text

        elif node_type == "heading":
            level = node.get("attrs", {}).get("level", 1)
            content_parts = []
            for item in node.get("content", []):
                content_parts.append(self._format_adf_node(item))
            heading_text = "".join(content_parts)
            return f"{'#' * level} {heading_text}"

        elif node_type == "bulletList":
            items = []
            for item in node.get("content", []):
                items.append(self._format_adf_node(item))
            return "\n".join(items)

        elif node_type == "orderedList":
            items = []
            for idx, item in enumerate(node.get("content", []), 1):
                formatted = self._format_adf_node(item)
                # Replace bullet with number
                formatted = formatted.replace("- ", f"{idx}. ", 1)
                items.append(formatted)
            return "\n".join(items)

        elif node_type == "listItem":
            content_parts = []
            for item in node.get("content", []):
                content_parts.append(self._format_adf_node(item))
            return f"- {''.join(content_parts)}"

        elif node_type == "codeBlock":
            language = node.get("attrs", {}).get("language", "")
            text_parts = []
            for item in node.get("content", []):
                if item.get("type") == "text":
                    text_parts.append(item.get("text", ""))
            code = "".join(text_parts)
            return f"```{language}\n{code}\n```"

        elif node_type == "blockquote":
            content_parts = []
            for item in node.get("content", []):
                content_parts.append(self._format_adf_node(item))
            quoted = "\n".join(content_parts)
            # Add > to each line
            return "\n".join(f"> {line}" for line in quoted.split("\n"))

        elif node_type == "hardBreak":
            return "\n"

        # Fallback for unknown types
        return f"[{node_type}]"

    def sync_all_issues(self, incremental: bool = True):
        """Sync all issues matching the JQL query."""
        logger.info(
            "Starting JIRA issue sync",
            output_dir=str(self.config.OUTPUT_DIR),
            incremental=incremental,
        )

        # Create output directory
        output_dir = Path(self.config.OUTPUT_DIR)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Load sync state for incremental sync
        sync_state = self._load_sync_state() if incremental else {}

        # Get all issues
        issues = self.search_issues()
        logger.info("Found issues to process", issue_count=len(issues))

        updated_count = 0
        new_count = 0
        skipped_count = 0

        for issue in issues:
            issue_key = issue.get("key", "")
            issue_hash = self._get_ticket_hash(issue)

            # Check if issue needs updating
            if incremental and issue_key in sync_state and sync_state[issue_key] == issue_hash:
                skipped_count += 1
                logger.debug("Issue unchanged, skipping", issue_key=issue_key)
                continue

            # Format and write issue
            content = self.format_issue_as_markdown(issue)

            # Create filename
            summary = issue.get("fields", {}).get("summary", "untitled")
            sanitized_summary = self._sanitize_filename(summary)
            filename = f"{issue_key}_{sanitized_summary}.md"
            filepath = output_dir / filename

            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)

            # Determine if new or updated
            was_existing = issue_key in sync_state
            sync_state[issue_key] = issue_hash

            if was_existing:
                updated_count += 1
                logger.debug("Issue updated", issue_key=issue_key)
            else:
                new_count += 1
                logger.debug("New issue synced", issue_key=issue_key)

        # Save sync state
        self._save_sync_state(sync_state)

        logger.info(
            "JIRA sync completed",
            new_issues=new_count,
            updated_issues=updated_count,
            skipped_issues=skipped_count,
            total_issues=len(issues),
        )


def main():
    """Main entry point for running JIRA sync standalone."""
    import argparse

    parser = argparse.ArgumentParser(description="Sync JIRA tickets")
    parser.add_argument("--full", action="store_true", help="Full sync (not incremental)")
    parser.add_argument("--jql", type=str, help="Custom JQL query")

    args = parser.parse_args()

    try:
        syncer = JIRASync()

        if args.jql:
            # Override JQL query
            syncer.config.JQL_QUERY = args.jql

        syncer.sync_all_issues(incremental=not args.full)

        return 0
    except Exception as e:
        logger.error(
            "Sync failed",
            error=str(e),
            error_type=type(e).__name__,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())

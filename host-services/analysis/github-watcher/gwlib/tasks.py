#!/usr/bin/env python3
"""Task execution for GitHub watcher services."""

import json
import secrets
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from jib_logging import get_logger

logger = get_logger("github-tasks")

MAX_PARALLEL_JIB = 20
HOST_NOTIFICATIONS_DIR = Path.home() / ".jib-sharing" / "notifications"


@dataclass
class JibTask:
    """A task to be executed by jib.

    Attributes:
        task_type: One of 'check_failure', 'comment', 'merge_conflict', 'review_request', 'pr_review_response'
        context: Task-specific context dict
        signature_key: Key for processed_* dict (e.g., 'processed_failures')
        signature_value: The signature to mark as processed
        is_readonly: If True, send notification instead of invoking jib
    """

    task_type: str
    context: dict
    signature_key: str
    signature_value: str
    is_readonly: bool = False


def invoke_jib(task_type: str, context: dict) -> bool:
    """Invoke jib container with context via jib --exec.

    Args:
        task_type: One of the supported task types
        context: Dict containing task-specific context

    Returns:
        True if invocation succeeded
    """
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    workflow_id = f"gw-{task_type}-{timestamp}-{secrets.token_hex(4)}"

    context["workflow_id"] = workflow_id
    context["workflow_type"] = task_type
    context_json = json.dumps(context)

    processor_path = "/home/jwies/khan/james-in-a-box/jib-container/jib-tasks/github/github-processor.py"
    cmd = ["jib", "--exec", "python3", processor_path, "--task", task_type, "--context", context_json]

    logger.info("Invoking jib", task_type=task_type, repository=context.get("repository"), pr_number=context.get("pr_number"))

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode == 0:
            logger.info("jib completed successfully", task_type=task_type)
            return True
        else:
            logger.error("jib failed", task_type=task_type, return_code=result.returncode, stderr=result.stderr[-2000:])
            return False
    except FileNotFoundError:
        logger.error("jib command not found")
        return False
    except Exception as e:
        logger.error("Error invoking jib", error=str(e))
        return False


def send_readonly_notification(task_type: str, context: dict) -> bool:
    """Send a Slack notification for a read-only repo event.

    Args:
        task_type: Type of task (comment, review_request, etc.)
        context: Task context dict

    Returns:
        True if notification was sent successfully
    """
    HOST_NOTIFICATIONS_DIR.mkdir(parents=True, exist_ok=True)

    repo = context.get("repository", "unknown")
    pr_number = context.get("pr_number", 0)
    pr_title = context.get("pr_title", "")
    pr_url = context.get("pr_url", "")

    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    task_id = f"readonly-{task_type}-{repo.replace('/', '-')}-{pr_number}-{timestamp}"

    # Build notification content based on task type
    title = f"{task_type.replace('_', ' ').title()} in {repo} PR #{pr_number}"
    body = f"**Repository**: {repo} _(read-only)_\n**PR**: [{pr_title}]({pr_url}) (#{pr_number})\n\n_This is a read-only repository._"

    file_content = f"""---
task_id: "{task_id}"
---

# {title}

{body}
"""

    filepath = HOST_NOTIFICATIONS_DIR / f"{timestamp}-{task_id}.md"

    try:
        filepath.write_text(file_content)
        logger.info("Read-only notification sent", task_type=task_type, repository=repo, pr_number=pr_number)
        return True
    except Exception as e:
        logger.error("Failed to write readonly notification", error=str(e))
        return False


def execute_task(task: JibTask, safe_state) -> bool:
    """Execute a single jib task and update state (thread-safe).

    Args:
        task: The JibTask to execute
        safe_state: ThreadSafeState instance

    Returns:
        True if task completed successfully
    """
    if task.is_readonly:
        if task.task_type == "review_request":
            task.context["is_readonly"] = True
            success = invoke_jib(task.task_type, task.context)
        else:
            success = send_readonly_notification(task.task_type, task.context)
    else:
        success = invoke_jib(task.task_type, task.context)

    if success:
        safe_state.mark_processed(task.signature_key, task.signature_value)
    else:
        safe_state.mark_failed(task.signature_value, task.task_type, task.context)
    return success


def execute_tasks_parallel(tasks: list[JibTask], safe_state) -> int:
    """Execute multiple jib tasks in parallel.

    Args:
        tasks: List of JibTask objects to execute
        safe_state: ThreadSafeState instance

    Returns:
        Number of successfully completed tasks
    """
    if not tasks:
        return 0

    completed = 0
    max_workers = min(MAX_PARALLEL_JIB, len(tasks))

    logger.info("Executing tasks in parallel", task_count=len(tasks), max_workers=max_workers)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_task = {executor.submit(execute_task, task, safe_state): task for task in tasks}
        for future in as_completed(future_to_task):
            try:
                if future.result():
                    completed += 1
            except Exception as e:
                task = future_to_task[future]
                logger.error("Task execution failed", task_type=task.task_type, error=str(e))

    logger.info("Parallel execution completed", completed=completed, total=len(tasks))
    return completed

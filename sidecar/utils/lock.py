"""workflow.lock — per-project mutex preventing concurrent workflow runs.

Lock file location: {project_path}/workflow.lock
Lock format: { "workflowId": str, "startedAt": ISO str, "pid": int }

Stale lock detection: if the PID in the lock file is no longer alive,
the lock is treated as stale and cleared automatically.
"""

import json
import os
import pathlib
from datetime import datetime, timezone


LOCK_FILENAME = "workflow.lock"


class WorkflowBusyError(RuntimeError):
    """Raised when another workflow is already running."""

    def __init__(self, workflow_id: str):
        self.workflow_id = workflow_id
        super().__init__(f"Workflow already running: {workflow_id}")


def _lock_path(project_path: str) -> pathlib.Path:
    return pathlib.Path(project_path) / LOCK_FILENAME


def _pid_alive(pid: int) -> bool:
    """Return True if the process with the given PID is alive."""
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        # ProcessLookupError → PID gone
        # PermissionError → PID exists but not owned by us (treat as alive)
        return isinstance(
            SystemError if False else PermissionError,
            PermissionError,
        )
    except OSError:
        return False


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        # Process exists but owned by another user — treat as alive
        return True
    except OSError:
        return False


async def acquire_lock(project_path: str, workflow_id: str) -> None:
    """Acquire the workflow lock.

    Raises WorkflowBusyError if another live workflow holds the lock.
    Silently clears stale locks (dead PID).
    """
    lock = _lock_path(project_path)

    if lock.exists():
        try:
            data = json.loads(lock.read_text(encoding="utf-8"))
            existing_pid = int(data.get("pid", 0))
            if existing_pid and _pid_alive(existing_pid):
                raise WorkflowBusyError(data.get("workflowId", "unknown"))
            # Stale lock — clear it
            lock.unlink(missing_ok=True)
        except (json.JSONDecodeError, KeyError, ValueError):
            # Corrupt lock file — clear it
            lock.unlink(missing_ok=True)

    lock.write_text(
        json.dumps(
            {
                "workflowId": workflow_id,
                "startedAt": datetime.now(timezone.utc).isoformat(),
                "pid": os.getpid(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )


async def release_lock(project_path: str) -> None:
    """Release the lock only if it belongs to the current process."""
    lock = _lock_path(project_path)
    if not lock.exists():
        return
    try:
        data = json.loads(lock.read_text(encoding="utf-8"))
        if int(data.get("pid", 0)) == os.getpid():
            lock.unlink(missing_ok=True)
    except (json.JSONDecodeError, ValueError):
        lock.unlink(missing_ok=True)


async def check_lock(project_path: str) -> dict | None:
    """Return the current lock dict, or None if no live lock exists."""
    lock = _lock_path(project_path)
    if not lock.exists():
        return None
    try:
        data = json.loads(lock.read_text(encoding="utf-8"))
        pid = int(data.get("pid", 0))
        if pid and not _pid_alive(pid):
            return None  # Stale — treat as unlocked
        return data
    except (json.JSONDecodeError, ValueError):
        return None


async def clear_stale_lock(project_path: str) -> bool:
    """Delete the lock file if its PID is dead. Returns True if cleared."""
    lock = _lock_path(project_path)
    if not lock.exists():
        return False
    try:
        data = json.loads(lock.read_text(encoding="utf-8"))
        pid = int(data.get("pid", 0))
        if pid and not _pid_alive(pid):
            lock.unlink(missing_ok=True)
            return True
    except (json.JSONDecodeError, ValueError):
        lock.unlink(missing_ok=True)
        return True
    return False

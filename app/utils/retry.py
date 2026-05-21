import json
import os
import time
from typing import Any, Callable, Optional

from app.config import WORKSPACE_DIR


class StageRetryError(RuntimeError):
    pass


def retry_stage(
    name: str,
    func: Callable[[], Any],
    *,
    attempts: int = 3,
    delay_seconds: float = 4.0,
    manifest: Optional[Any] = None,
) -> Any:
    """
    Retries one pipeline stage and records failures so a run can recover from
    transient browser/network/API hiccups without regenerating earlier stages.
    """
    os.makedirs(WORKSPACE_DIR, exist_ok=True)
    queue_path = os.path.join(WORKSPACE_DIR, "stage_retry_queue.json")
    failures = []

    if manifest:
        manifest.stage_started(name, {"max_attempts": attempts})

    last_error: Optional[BaseException] = None
    for attempt in range(1, attempts + 1):
        try:
            result = func()
            if not result:
                raise StageRetryError(f"{name} returned no result")
            if manifest:
                manifest.stage_attempt(name, attempt, "success")
                manifest.stage_completed(name)
            return result
        except Exception as exc:
            last_error = exc
            failure = {
                "stage": name,
                "attempt": attempt,
                "error": str(exc),
                "timestamp": int(time.time()),
            }
            failures.append(failure)
            if manifest:
                manifest.stage_attempt(name, attempt, "failed", {"error": str(exc)})
            with open(queue_path, "w", encoding="utf-8") as f:
                json.dump({"pending_or_failed": failures}, f, indent=2)
            print(f"{name} attempt {attempt}/{attempts} failed: {exc}")
            if attempt < attempts:
                time.sleep(delay_seconds * attempt)

    if manifest and last_error:
        manifest.stage_failed(name, last_error, {"attempts": attempts})
    raise StageRetryError(f"{name} failed after {attempts} attempts: {last_error}")

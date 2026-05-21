import json
import os
import time
import traceback
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.config import WORKSPACE_DIR


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class RunManifest:
    """Small JSON ledger for each automation run."""

    def __init__(self, name: str = "latest_run_manifest.json"):
        self.path = os.path.join(WORKSPACE_DIR, name)
        self.data: Dict[str, Any] = {
            "run_id": str(int(time.time())),
            "started_at": utc_now_iso(),
            "status": "running",
            "stages": {},
            "artifacts": {},
            "errors": [],
        }
        self.save()

    def save(self) -> None:
        os.makedirs(WORKSPACE_DIR, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2)

    def set_artifact(self, key: str, value: Any) -> None:
        self.data.setdefault("artifacts", {})[key] = value
        self.save()

    def stage_started(self, name: str, details: Optional[Dict[str, Any]] = None) -> None:
        self.data.setdefault("stages", {})[name] = {
            "status": "running",
            "started_at": utc_now_iso(),
            "attempts": [],
            "details": details or {},
        }
        self.save()

    def stage_attempt(self, name: str, attempt: int, status: str, details: Optional[Dict[str, Any]] = None) -> None:
        stage = self.data.setdefault("stages", {}).setdefault(name, {})
        stage.setdefault("attempts", []).append({
            "attempt": attempt,
            "status": status,
            "at": utc_now_iso(),
            "details": details or {},
        })
        self.save()

    def stage_completed(self, name: str, details: Optional[Dict[str, Any]] = None) -> None:
        stage = self.data.setdefault("stages", {}).setdefault(name, {})
        stage["status"] = "completed"
        stage["completed_at"] = utc_now_iso()
        if details:
            stage.setdefault("details", {}).update(details)
        self.save()

    def stage_failed(self, name: str, error: BaseException, details: Optional[Dict[str, Any]] = None) -> None:
        stage = self.data.setdefault("stages", {}).setdefault(name, {})
        stage["status"] = "failed"
        stage["failed_at"] = utc_now_iso()
        stage["error"] = str(error)
        if details:
            stage.setdefault("details", {}).update(details)
        self.data.setdefault("errors", []).append({
            "stage": name,
            "error": str(error),
            "traceback": traceback.format_exc(limit=8),
            "at": utc_now_iso(),
        })
        self.save()

    def finish(self, status: str = "completed") -> None:
        self.data["status"] = status
        self.data["finished_at"] = utc_now_iso()
        self.save()

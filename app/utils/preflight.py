import json
import os
import shutil
import subprocess
from typing import Any, Dict, List

import requests

from app.config import (
    GEMINI_API_KEY,
    WORKSPACE_DIR,
    YOUTUBE_CLIENT_ID,
    YOUTUBE_CLIENT_SECRET,
    YOUTUBE_REFRESH_TOKEN,
)


def _check_chrome_cdp() -> Dict[str, Any]:
    try:
        response = requests.get("http://localhost:9222/json/version", timeout=2)
        if response.status_code == 200:
            data = response.json()
            return {"ok": True, "browser": data.get("Browser"), "websocket": bool(data.get("webSocketDebuggerUrl"))}
        return {"ok": False, "error": f"HTTP {response.status_code}"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _check_kimi() -> Dict[str, Any]:
    try:
        response = requests.get("http://127.0.0.1:10086/status", timeout=2)
        if response.status_code != 200:
            return {"ok": False, "error": f"HTTP {response.status_code}"}
        data = response.json()
        return {
            "ok": bool(data.get("running") and data.get("extension_connected")),
            "status": data,
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _check_ffmpeg() -> Dict[str, Any]:
    ffmpeg = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
    ffprobe = shutil.which("ffprobe") or "/opt/homebrew/bin/ffprobe"
    ok = os.path.exists(ffmpeg) and os.path.exists(ffprobe)
    return {"ok": ok, "ffmpeg": ffmpeg if os.path.exists(ffmpeg) else None, "ffprobe": ffprobe if os.path.exists(ffprobe) else None}


def _check_workspace() -> Dict[str, Any]:
    try:
        os.makedirs(WORKSPACE_DIR, exist_ok=True)
        probe = os.path.join(WORKSPACE_DIR, ".preflight_write_probe")
        with open(probe, "w", encoding="utf-8") as f:
            f.write("ok")
        os.remove(probe)
        return {"ok": True, "path": WORKSPACE_DIR}
    except Exception as exc:
        return {"ok": False, "path": WORKSPACE_DIR, "error": str(exc)}


def _check_python() -> Dict[str, Any]:
    try:
        output = subprocess.check_output(["python3", "--version"], text=True).strip()
        return {"ok": True, "version": output}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def run_preflight(strict: bool = True) -> Dict[str, Any]:
    """
    Checks the pieces that usually break unattended runs before spending time on
    product/video generation.
    """
    report: Dict[str, Any] = {
        "checks": {
            "workspace": _check_workspace(),
            "python": _check_python(),
            "ffmpeg": _check_ffmpeg(),
            "gemini_api_key": {"ok": bool(GEMINI_API_KEY)},
            "youtube_oauth": {"ok": bool(YOUTUBE_CLIENT_ID and YOUTUBE_CLIENT_SECRET and YOUTUBE_REFRESH_TOKEN)},
            "chrome_cdp": _check_chrome_cdp(),
            "kimi_webbridge": _check_kimi(),
        },
        "warnings": [],
        "critical_failures": [],
    }

    checks = report["checks"]
    critical_names: List[str] = ["workspace", "ffmpeg", "gemini_api_key", "youtube_oauth"]
    for name in critical_names:
        if not checks[name].get("ok"):
            report["critical_failures"].append(name)

    if not (checks["chrome_cdp"].get("ok") or checks["kimi_webbridge"].get("ok")):
        report["critical_failures"].append("browser_automation")

    if checks["python"].get("version", "").startswith("Python 3.9"):
        report["warnings"].append("Python 3.9 is end-of-life; upgrade to Python 3.10+ for Google client library support.")

    if not checks["kimi_webbridge"].get("ok"):
        report["warnings"].append("Kimi WebBridge is unavailable; Chrome CDP fallback must handle browser automation.")

    report["ok"] = not report["critical_failures"]
    path = os.path.join(WORKSPACE_DIR, "preflight_report.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"Saved preflight report: {path}")

    if strict and not report["ok"]:
        raise RuntimeError(f"Preflight failed: {', '.join(report['critical_failures'])}")
    return report

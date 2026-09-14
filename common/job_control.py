"""Estado e cancelamento de backups compartilhados entre os containers."""

import json
import os
import re
import time
import uuid
from pathlib import Path

CONTROL_DIR = Path(os.getenv("JOB_CONTROL_DIR", "/app/logs/control"))


def _safe(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", value)


def _status_path(vendor: str) -> Path:
    return CONTROL_DIR / f"{_safe(vendor)}.json"


def _cancel_path(vendor: str) -> Path:
    return CONTROL_DIR / f"{_safe(vendor)}.cancel"


def start_job(vendor: str, source: str, target: str | None = None) -> str:
    CONTROL_DIR.mkdir(parents=True, exist_ok=True)
    clear_cancel(vendor)
    job_id = uuid.uuid4().hex
    state = {
        "id": job_id,
        "vendor": vendor,
        "target": target,
        "source": source,
        "state": "running",
        "started_at": int(time.time()),
        "updated_at": int(time.time()),
    }
    path = _status_path(vendor)
    tmp = path.with_suffix(f".{job_id}.tmp")
    tmp.write_text(json.dumps(state), encoding="utf-8")
    tmp.replace(path)
    return job_id


def finish_job(vendor: str, job_id: str) -> None:
    path = _status_path(vendor)
    try:
        current = json.loads(path.read_text(encoding="utf-8"))
        if current.get("id") == job_id:
            path.unlink(missing_ok=True)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    clear_cancel(vendor)


def touch_job(vendor: str, job_id: str) -> None:
    path = _status_path(vendor)
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
        if state.get("id") != job_id:
            return
        state["updated_at"] = int(time.time())
        tmp = path.with_suffix(f".{job_id}.tmp")
        tmp.write_text(json.dumps(state), encoding="utf-8")
        tmp.replace(path)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass


def read_job(vendor: str, max_age: int = 90) -> dict | None:
    try:
        state = json.loads(_status_path(vendor).read_text(encoding="utf-8"))
        if state.get("state") != "running":
            return None
        if int(time.time()) - int(state.get("updated_at", state.get("started_at", 0))) > max_age:
            _status_path(vendor).unlink(missing_ok=True)
            return None
        return state
    except (FileNotFoundError, json.JSONDecodeError, OSError, ValueError, TypeError):
        return None


def request_cancel(vendor: str) -> None:
    CONTROL_DIR.mkdir(parents=True, exist_ok=True)
    _cancel_path(vendor).write_text(str(int(time.time())), encoding="ascii")


def is_cancelled(vendor: str) -> bool:
    return _cancel_path(vendor).exists()


def clear_cancel(vendor: str) -> None:
    _cancel_path(vendor).unlink(missing_ok=True)


def terminate_process(proc, grace_seconds: int = 5) -> None:
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=grace_seconds)
    except Exception:
        proc.kill()
        proc.wait(timeout=grace_seconds)

"""Persistência local do histórico de backups e telemetria SNMP."""

import contextvars
import json
import logging
import os
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta
from functools import wraps
from pathlib import Path


_current_run = contextvars.ContextVar("backup_run", default=None)


def db_path() -> Path:
    return Path(os.getenv("BKPOLTS_DB", "/app/data/bkpolts.db"))


def connect() -> sqlite3.Connection:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=15000")
    return conn


def init_db() -> None:
    with closing(connect()) as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS backup_runs (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          vendor TEXT NOT NULL, olt_name TEXT NOT NULL, ip TEXT,
          protocol TEXT, source TEXT, started_at TEXT NOT NULL,
          finished_at TEXT, status TEXT NOT NULL DEFAULT 'running',
          error_message TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_backup_started ON backup_runs(started_at DESC);
        CREATE INDEX IF NOT EXISTS idx_backup_olt ON backup_runs(olt_name, started_at DESC);
        CREATE TABLE IF NOT EXISTS snmp_samples (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          olt_name TEXT NOT NULL, vendor TEXT NOT NULL, ip TEXT NOT NULL,
          collected_at TEXT NOT NULL, reachable INTEGER NOT NULL,
          sys_name TEXT, sys_description TEXT, uptime_ticks INTEGER,
          error_message TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_snmp_olt ON snmp_samples(olt_name, collected_at DESC);
        """)
        conn.commit()


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def start_backup_run(vendor: str, olt: dict, protocol: str) -> int:
    init_db()
    with closing(connect()) as conn:
        conn.execute("""UPDATE backup_runs SET finished_at=?,status='cancelled',
                     error_message=COALESCE(error_message,'Execução anterior foi interrompida')
                     WHERE vendor=? AND olt_name=? AND status='running'""",
                     (_now(), vendor, olt.get("name", "OLT")))
        cur = conn.execute(
            "INSERT INTO backup_runs(vendor,olt_name,ip,protocol,source,started_at) VALUES(?,?,?,?,?,?)",
            (vendor, olt.get("name", "OLT"), olt.get("ip", ""), protocol,
             os.getenv("BACKUP_SOURCE", "scheduler"), _now()),
        )
        conn.commit()
        return int(cur.lastrowid)


def finish_backup_run(run_id: int, status: str, error: str | None = None) -> None:
    with closing(connect()) as conn:
        row = conn.execute("SELECT error_message FROM backup_runs WHERE id=?", (run_id,)).fetchone()
        message = ((row[0] if row else None) or error)
        conn.execute(
            "UPDATE backup_runs SET finished_at=?, status=?, error_message=? WHERE id=?",
            (_now(), status, (message or "")[:1000] or None, run_id),
        )
        conn.commit()


def cancel_running_runs(vendor: str, olt_name: str | None = None) -> None:
    """Marca no histórico processos interrompidos externamente pelo painel."""
    init_db()
    query = """UPDATE backup_runs SET finished_at=?,status='cancelled',
               error_message=COALESCE(error_message,'Cancelado manualmente pelo operador')
               WHERE vendor=? AND status='running'"""
    params = [_now(), vendor]
    if olt_name:
        query += " AND olt_name=?"
        params.append(olt_name)
    with closing(connect()) as conn:
        conn.execute(query, params)
        conn.commit()


def record_current_error(message: str) -> None:
    run_id = _current_run.get()
    if not run_id:
        return
    try:
        with closing(connect()) as conn:
            for key, secret in os.environ.items():
                if secret and any(word in key.upper() for word in ("PASS", "TOKEN", "SECRET", "COMMUNITY")):
                    message = message.replace(secret, "****")
            conn.execute("UPDATE backup_runs SET error_message=? WHERE id=?", (message[:1000], run_id))
            conn.commit()
    except sqlite3.Error:
        pass


class HistoryErrorHandler(logging.Handler):
    def emit(self, record):
        if record.levelno >= logging.ERROR:
            message = record.getMessage()
            if record.exc_info:
                message += ": " + logging.Formatter().formatException(record.exc_info).splitlines()[-1]
            record_current_error(message)


def tracked_backup(vendor: str, protocol: str):
    """Decorator para registrar início, resultado e último erro de cada OLT."""
    def decorate(func):
        @wraps(func)
        def wrapped(olt, *args, **kwargs):
            run_id = start_backup_run(vendor, olt, protocol)
            token = _current_run.set(run_id)
            try:
                result = func(olt, *args, **kwargs)
                finish_backup_run(run_id, "success" if result else "failure",
                                  None if result else "Backup não concluído; verifique o erro e o log em tempo real")
                return result
            except BaseException as exc:
                finish_backup_run(run_id, "cancelled" if isinstance(exc, KeyboardInterrupt) else "error", str(exc))
                raise
            finally:
                _current_run.reset(token)
        return wrapped
    return decorate


def record_snmp_sample(device: dict, reachable: bool, values=None, error: str | None = None):
    init_db()
    values = values or {}
    with closing(connect()) as conn:
        conn.execute("""
          INSERT INTO snmp_samples(olt_name,vendor,ip,collected_at,reachable,sys_name,
            sys_description,uptime_ticks,error_message) VALUES(?,?,?,?,?,?,?,?,?)
        """, (device["name"], device["vendor"], device["ip"], _now(), int(reachable),
              values.get("sys_name"), values.get("sys_description"), values.get("uptime_ticks"),
              (error or "")[:500] or None))
        conn.commit()


def latest_snmp() -> dict:
    init_db()
    with closing(connect()) as conn:
        rows = conn.execute("""
          SELECT s.* FROM snmp_samples s JOIN (
            SELECT olt_name, MAX(id) id FROM snmp_samples GROUP BY olt_name
          ) latest ON latest.id=s.id
        """).fetchall()
    return {row["olt_name"]: dict(row) for row in rows}


def dashboard_data(days: int = 7, limit: int = 12) -> dict:
    init_db()
    since = (datetime.now().astimezone() - timedelta(days=days - 1)).date()
    with closing(connect()) as conn:
        recent = [dict(r) for r in conn.execute(
            "SELECT * FROM backup_runs ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()]
        totals = {r["status"]: r["n"] for r in conn.execute(
            "SELECT status,COUNT(*) n FROM backup_runs WHERE started_at>=? GROUP BY status",
            (since.isoformat(),),
        )}
        raw = conn.execute("""
          SELECT substr(started_at,1,10) day,status,COUNT(*) n FROM backup_runs
          WHERE started_at>=? GROUP BY day,status ORDER BY day
        """, (since.isoformat(),)).fetchall()
    by_day = {str(since + timedelta(days=i)): {"success": 0, "failure": 0, "error": 0, "cancelled": 0}
              for i in range(days)}
    for row in raw:
        if row["day"] in by_day:
            by_day[row["day"]][row["status"]] = row["n"]
    return {"recent": recent, "totals": totals,
            "chart": [{"day": day, **values} for day, values in by_day.items()]}

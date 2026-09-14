#!/usr/bin/env python3
"""Coleta identificação e uptime das OLTs via SNMP v2c."""

import json
import os
import subprocess
import time
import re
from pathlib import Path

from common.env_store import load_env, parse_olts_raw
from common.observability import record_snmp_sample
from common.vendors import VENDORS

ENV_FILE = Path(os.getenv("ENV_FILE", "/app/.env"))
OIDS = {
    "sys_description": ".1.3.6.1.2.1.1.1.0",
    "uptime_ticks": ".1.3.6.1.2.1.1.3.0",
    "sys_name": ".1.3.6.1.2.1.1.5.0",
}


def devices_from_env(env: dict) -> list[dict]:
    devices = []
    for vendor, definition in VENDORS.items():
        for model in definition["models"]:
            disabled = {n.strip() for n in env.get(f'{model["env_var"]}_DISABLED', '').split(',') if n.strip()}
            for olt in parse_olts_raw(env.get(model["env_var"], "")):
                if olt["name"] not in disabled:
                    devices.append({**olt, "vendor": vendor})
    return devices


def communities(env: dict) -> dict:
    try:
        mapping = json.loads(env.get("SNMP_COMMUNITIES_JSON", "{}"))
        return mapping if isinstance(mapping, dict) else {}
    except json.JSONDecodeError:
        return {}


def collect(device: dict, community: str) -> tuple[bool, dict, str | None]:
    if not community:
        return False, {}, "Community SNMP não configurada para este IP"
    command = ["snmpget", "-v2c", "-c", community, "-Oqv", "-t", "2", "-r", "1",
               device["ip"], *OIDS.values()]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=12)
        if result.returncode != 0:
            return False, {}, (result.stderr.strip() or "Sem resposta SNMP")
        lines = result.stdout.splitlines()
        if len(lines) < 3:
            return False, {}, "Resposta SNMP incompleta"
        uptime_match = re.search(r"\((\d+)\)", lines[1])
        return True, {"sys_description": lines[0].strip('"'),
                      "uptime_ticks": int(uptime_match.group(1)) if uptime_match else 0,
                      "sys_name": lines[2].strip('"')}, None
    except subprocess.TimeoutExpired:
        return False, {}, "Tempo limite excedido na coleta SNMP"
    except OSError as exc:
        return False, {}, f"Falha ao executar cliente SNMP: {exc}"


def collect_once():
    env = load_env(ENV_FILE)
    mapping = communities(env)
    default = env.get("SNMP_COMMUNITY", "")
    for device in devices_from_env(env):
        ok, values, error = collect(device, mapping.get(device["ip"], default))
        record_snmp_sample(device, ok, values, error)


if __name__ == "__main__":
    interval = max(30, int(os.getenv("SNMP_INTERVAL_SECONDS", "300")))
    while True:
        collect_once()
        time.sleep(interval)

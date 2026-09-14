#!/usr/bin/env python3
"""Importa inventário normalizado ou export de hosts do Zabbix para o .env."""

import argparse
import getpass
import json
import os
import re
import sys
from pathlib import Path

from common.env_store import load_env, parse_olts_raw, save_env, serialize_olts
from common.vendors import VENDORS

BASE_DIR = Path(__file__).resolve().parent
ENV_FILE = BASE_DIR / ".env"


def safe_name(value: str) -> str:
    name = re.sub(r"[^A-Za-z0-9_-]+", "_", value.strip()).strip("_")
    return name.upper() or "OLT"


def detect_device(host: dict) -> dict | None:
    name = host.get("name") or host.get("host") or ""
    groups = " ".join(g.get("name", "") for g in host.get("groups", []))
    templates = " ".join(t.get("name", "") for t in host.get("templates", []))
    text = f"{name} {groups} {templates}".lower()
    vendor = next((item for item in ("datacom", "huawei", "zte") if item in text), None)
    if not vendor:
        return None
    ip = next((i.get("ip") for i in host.get("interfaces", []) if i.get("ip")), "")
    if not ip:
        return None
    if vendor == "zte":
        model = "titan" if "titan" in text or re.search(r"\bc6\d{2}\b", text) else "c3xx"
    elif vendor == "datacom":
        model = "dmos"
    else:
        model = "ma5xxx"
    return {"name": safe_name(name), "ip": ip, "vendor": vendor, "model": model}


def load_devices(path: Path) -> tuple[list[dict], str]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if "devices" in data:
        return data["devices"], data.get("username", "bkpolt")
    hosts = data.get("zabbix_export", {}).get("hosts", [])
    return [device for host in hosts if (device := detect_device(host))], "bkpolt"


def model_env_var(vendor: str, model_key: str) -> str:
    for model in VENDORS.get(vendor, {}).get("models", []):
        if model["key"] == model_key:
            return model["env_var"]
    raise ValueError(f"Modelo não suportado: {vendor}/{model_key}")


def import_devices(devices: list[dict], username: str, password: str, env_file: Path) -> dict:
    env = load_env(env_file)
    grouped: dict[str, list[dict]] = {}
    counts = {"added": 0, "updated": 0, "ignored": 0}
    for device in devices:
        try:
            env_var = model_env_var(device["vendor"], device["model"])
        except (KeyError, ValueError):
            counts["ignored"] += 1
            continue
        grouped.setdefault(env_var, []).append(device)

    updates = {}
    enabled_vendors = {v.strip() for v in env.get("VENDOR", "").split(",") if v.strip()}
    for env_var, incoming in grouped.items():
        current = parse_olts_raw(env.get(env_var, ""))
        by_ip = {olt["ip"]: index for index, olt in enumerate(current)}
        for device in incoming:
            if device["ip"] in by_ip:
                existing = current[by_ip[device["ip"]]]
                existing["user"] = username
                existing["password"] = password
                counts["updated"] += 1
            else:
                current.append({
                    "name": safe_name(device["name"]), "ip": device["ip"],
                    "user": username, "password": password,
                })
                counts["added"] += 1
        updates[env_var] = serialize_olts(current)
        for vendor, definition in VENDORS.items():
            if any(model["env_var"] == env_var for model in definition["models"]):
                enabled_vendors.add(vendor)
                break
    updates["VENDOR"] = ",".join(v for v in VENDORS if v in enabled_vendors)
    save_env(env_file, updates)
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description="Importa OLTs do Zabbix/inventário sem duplicar IPs")
    parser.add_argument("inventory", type=Path)
    parser.add_argument("--username")
    parser.add_argument("--password-stdin", action="store_true")
    parser.add_argument("--env-file", type=Path, default=ENV_FILE)
    args = parser.parse_args()
    devices, default_user = load_devices(args.inventory)
    username = args.username or os.getenv("IMPORT_USERNAME") or default_user
    if args.password_stdin:
        password = sys.stdin.readline().rstrip("\r\n")
    else:
        password = os.getenv("IMPORT_PASSWORD") or getpass.getpass(f"Senha das OLTs para {username}: ")
    if not password:
        parser.error("senha vazia")
    counts = import_devices(devices, username, password, args.env_file)
    print(f"Importação concluída: {counts['added']} adicionada(s), "
          f"{counts['updated']} atualizada(s), {counts['ignored']} ignorada(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

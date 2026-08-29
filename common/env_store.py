"""
Leitura/escrita do arquivo .env preservando comentários e ordem das linhas.

Usado pela interface web para cadastrar OLTs sem exigir edição manual do
.env. O formato de OLTs (NOME:IP:USUARIO:SENHA separados por vírgula) é o
mesmo usado por common/parser.py — por isso as validações aqui existem:
um nome/IP/usuário com ":" ou "," quebraria o parser.
"""

import re
from pathlib import Path

OLT_FIELD_RE = re.compile(r"^[^:,/]+$")


def load_env(env_file: Path) -> dict:
    """Carrega variáveis do .env como um dict simples."""
    env = {}
    if not env_file.exists():
        return env
    with open(env_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def save_env(env_file: Path, updates: dict):
    """Atualiza ou adiciona variáveis no .env sem apagar comentários/ordem."""
    lines = []
    if env_file.exists():
        with open(env_file, encoding="utf-8") as f:
            lines = f.readlines()

    updated_keys = set()
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            new_lines.append(line)
            continue
        key = stripped.split("=", 1)[0].strip()
        if key in updates:
            new_lines.append(f"{key}={updates[key]}\n")
            updated_keys.add(key)
        else:
            new_lines.append(line)

    for key, value in updates.items():
        if key not in updated_keys:
            new_lines.append(f"{key}={value}\n")

    with open(env_file, "w", encoding="utf-8") as f:
        f.writelines(new_lines)


def validate_olt_field(value: str, field_label: str) -> str | None:
    """Retorna uma mensagem de erro se o campo quebrar o formato NOME:IP:USER:PASS,..."""
    if not value.strip():
        return f"{field_label} não pode ficar em branco."
    if not OLT_FIELD_RE.match(value):
        return f"{field_label} não pode conter ':', ',' ou '/'."
    return None


def validate_olt_password(value: str) -> str | None:
    """Senha pode conter ':' (o parser junta tudo após o 3º ':'), mas não ','."""
    if not value:
        return "Senha não pode ficar em branco."
    if "," in value:
        return "Senha não pode conter ','."
    return None


def parse_olts_raw(raw: str) -> list[dict]:
    """Mesma lógica de common/parser.py, mas operando sobre uma string (não env var)."""
    olts = []
    for entry in (raw or "").split(","):
        entry = entry.strip()
        if not entry:
            continue
        parts = entry.split(":")
        if len(parts) < 4:
            continue
        olts.append({
            "name": parts[0].strip(),
            "ip": parts[1].strip(),
            "user": parts[2].strip(),
            "password": ":".join(parts[3:]).strip(),
        })
    return olts


def serialize_olts(olts: list[dict]) -> str:
    return ",".join(f"{o['name']}:{o['ip']}:{o['user']}:{o['password']}" for o in olts)

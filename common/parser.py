"""
Parser de OLTs a partir de variáveis de ambiente.

Formato no .env:
  VENDOR_OLTS=NOME1:IP:USER:PASS,NOME2:IP:USER:PASS

Retorna lista de dicts:
  [{"name": "NOME1", "ip": "IP", "user": "USER", "password": "PASS"}, ...]
"""

import os
import logging

log = logging.getLogger("olt-backup")


def parse_olts(env_var: str) -> list[dict]:
    """
    Lê a variável de ambiente e retorna a lista de OLTs.
    Formato: NOME:IP:USUARIO:SENHA separados por vírgula.
    """
    raw = os.getenv(env_var, "").strip()
    if not raw:
        log.warning("Variável %s vazia ou não definida.", env_var)
        return []

    olts = []
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        parts = entry.split(":")
        if len(parts) < 4:
            log.warning("Entrada inválida (esperado NOME:IP:USER:PASS): '%s'", entry)
            continue
        # Senha pode conter ":" — junta tudo após o 3º ":"
        name = parts[0].strip()
        ip = parts[1].strip()
        user = parts[2].strip()
        password = ":".join(parts[3:]).strip()
        olts.append({
            "name": name,
            "ip": ip,
            "user": user,
            "password": password,
        })

    log.info("Parsed %d OLT(s) de %s", len(olts), env_var)
    return olts

#!/usr/bin/env python3
"""Backup de OLTs Fiberhome — Telnet + FTP

Fluxo por OLT:
  1. Conecta via Telnet, aguarda prompt "Login:"
  2. Envia usuário, aguarda "Password:", envia senha
  3. Aguarda prompt "User>", envia "enable"
  4. Aguarda "Password:" do enable, envia a mesma senha
  5. Aguarda prompt "Admin#", executa o upload FTP:
       upload ftp system <IP> <USER> <PASS> <FILENAME>
  6. Aguarda 30s para o upload concluir na OLT
  7. Baixa o arquivo do FTP, envia ao Telegram e limpa

Variáveis de ambiente necessárias:
  FIBERHOME_OLTS — formato NOME:IP:USER:PASS separados por vírgula
  FTP_IP, FTP_USER, FTP_PASSWORD
"""

import os
import sys
import time
import telnetlib
from datetime import datetime

sys.path.insert(0, "/app")

from common.helpers import ftp_download_rename, cleanup_file, setup_logging
from common.telegram import send_message, send_file
from common.parser import parse_olts

log = setup_logging("fiberhome")

FTP_IP       = os.getenv("FTP_IP", "")
FTP_USER     = os.getenv("FTP_USER", "")
FTP_PASSWORD = os.getenv("FTP_PASSWORD", "")

TIMEOUT = 20   # timeout geral de leitura de prompts
UPLOAD_WAIT = 30  # segundos aguardando o upload FTP concluir na OLT


def write(tn: telnetlib.Telnet, cmd: str):
    """Envia um comando + newline e loga."""
    log.info("CMD >> %s", cmd if "password" not in cmd.lower() else "****")
    tn.write(cmd.encode("ascii") + b"\n")


def read_until(tn: telnetlib.Telnet, expected: bytes, timeout: int = TIMEOUT) -> str:
    """Aguarda um prompt e retorna o texto recebido."""
    data = tn.read_until(expected, timeout=timeout).decode("ascii", errors="ignore")
    log.info("RESP << %s", data.strip()[:200])
    return data


def backup_fiberhome(olt: dict, progresso: str) -> bool:
    name = olt["name"]
    ip   = olt["ip"]
    user = olt["user"]
    password = olt["password"]

    send_message(f"🔄 {progresso} Iniciando backup Fiberhome — {name} ({ip})")
    log.info("===== INÍCIO BACKUP FIBERHOME %s (%s) =====", name, ip)

    try:
        tn = telnetlib.Telnet(ip, 23, timeout=TIMEOUT)

        # ── Login ──────────────────────────────────────────────────
        read_until(tn, b"Login:")
        write(tn, user)

        read_until(tn, b"Password:")
        write(tn, password)

        # ── Aguarda prompt User> ───────────────────────────────────
        read_until(tn, b"User>")

        # ── Entra no modo enable ───────────────────────────────────
        write(tn, "enable")

        read_until(tn, b"Password:")
        write(tn, password)

        # ── Aguarda prompt Admin# ──────────────────────────────────
        read_until(tn, b"Admin#")

        # ── Monta nome do arquivo e executa upload FTP ─────────────
        ts_file = datetime.now().strftime("%d%m%Y")
        ftp_filename = f"backupoltfiberhome{ts_file}.cfg"

        backup_cmd = (
            f"upload ftp system {FTP_IP} "
            f"{FTP_USER} {FTP_PASSWORD} {ftp_filename}"
        )
        write(tn, backup_cmd)

        # ── Aguarda conclusão do upload na OLT ─────────────────────
        log.info("Aguardando %ds para upload FTP concluir...", UPLOAD_WAIT)
        time.sleep(UPLOAD_WAIT)

        # Lê resposta final (Finished. / You've successfully...)
        resp = tn.read_very_eager().decode("ascii", errors="ignore")
        if resp.strip():
            log.info("RESP << %s", resp.strip()[:300])

        # ── Encerra sessão ─────────────────────────────────────────
        write(tn, "exit")
        tn.close()

        # ── Baixa do FTP e envia ao Telegram ───────────────────────
        local_file = ftp_download_rename(
            FTP_IP, FTP_USER, FTP_PASSWORD,
            ftp_filename, name, extension="cfg"
        )

        if local_file:
            fname = os.path.basename(local_file)
            send_file(local_file, caption=f"📦 Backup {name} — {fname}")
            send_message(f"✅ {progresso} {name} — backup concluído")
            cleanup_file(local_file)
            return True
        else:
            send_message(f"⚠️ {progresso} {name} — upload enviado mas falha ao baixar do FTP")
            return False

    except Exception as exc:
        log.exception("Erro no backup Fiberhome %s", name)
        send_message(f"❌ {progresso} {name} — falha: {exc}")
        return False


def main():
    olts = parse_olts("FIBERHOME_OLTS")
    total = len(olts)
    if total == 0:
        send_message("⚠️ Fiberhome: nenhuma OLT configurada em FIBERHOME_OLTS")
        return

    ts = datetime.now().strftime("%d/%m/%Y %H:%M")
    send_message(f"🚀 Iniciando backup de {total} OLT(s) Fiberhome — {ts}")

    ok_list, fail_list = [], []
    for idx, olt in enumerate(olts, start=1):
        prog = f"[{idx}/{total}]"
        if backup_fiberhome(olt, prog):
            ok_list.append(olt["name"])
        else:
            fail_list.append(olt["name"])
        if idx < total:
            log.info("Aguardando 10s antes da próxima OLT...")
            time.sleep(10)

    resumo = (
        f"📋 Resumo Fiberhome — {datetime.now().strftime('%d/%m/%Y %H:%M')}\n"
        f"✅ Sucesso ({len(ok_list)}): {', '.join(ok_list) or 'nenhum'}\n"
        f"❌ Falha ({len(fail_list)}): {', '.join(fail_list) or 'nenhum'}"
    )
    send_message(resumo)


if __name__ == "__main__":
    main()

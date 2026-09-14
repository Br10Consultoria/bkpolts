#!/usr/bin/env python3
"""Backup de OLTs Huawei — Telnet + FTP

Fluxo por OLT:
  1. Conecta via Telnet, aguarda "username:"
  2. Envia usuário, aguarda "password:", envia senha
  3. Envia "enable", aguarda prompt "#"
  4. Executa: backup configuration ftp <FTP_IP> <FILENAME>
  5. Aguarda "Are you sure to continue? (y/n)" e envia "y"
  6. Aguarda 30s para o upload FTP concluir na OLT
  7. Envia "exit" e fecha a sessão
  8. Baixa o arquivo do FTP e envia ao Telegram

Variáveis de ambiente necessárias:
  HUAWEI_OLTS  — formato NOME:IP:USER:PASS separados por vírgula
  FTP_IP, FTP_USER, FTP_PASSWORD
"""

import os
import sys
import time
import telnetlib
from datetime import datetime

sys.path.insert(0, "/app")

from common.helpers import ftp_download_rename, cleanup_file, setup_logging, redact_secrets
from common.telegram import send_message, send_file
from common.parser import parse_olts
from common.observability import tracked_backup

log = setup_logging("huawei")

FTP_IP       = os.getenv("FTP_IP", "")
FTP_USER     = os.getenv("FTP_USER", "")
FTP_PASSWORD = os.getenv("FTP_PASSWORD", "")

UPLOAD_WAIT  = 30   # segundos aguardando o upload FTP concluir na OLT


@tracked_backup("huawei", "ftp")
def backup_huawei(olt: dict, progresso: str) -> bool:
    name     = olt["name"]
    ip       = olt["ip"]
    user     = olt["user"]
    password = olt["password"]

    send_message(f"🔄 {progresso} Iniciando backup Huawei — {name} ({ip})")
    log.info("===== INÍCIO BACKUP HUAWEI %s (%s) =====", name, ip)

    try:
        tn = telnetlib.Telnet(ip, 23, timeout=20)

        # ── Login ──────────────────────────────────────────────────
        tn.read_until(b"username:", timeout=10)
        tn.write(user.encode("ascii") + b"\n")
        log.info("CMD >> %s", user)

        tn.read_until(b"password:", timeout=10)
        tn.write(password.encode("ascii") + b"\n")
        log.info("CMD >> ****")

        # ── Modo privilegiado ──────────────────────────────────────
        tn.write(b"enable\n")
        log.info("CMD >> enable")
        tn.read_until(b"#", timeout=10)

        # ── Monta nome do arquivo ──────────────────────────────────
        # Formato: backupolt<NOME><DDMMYYYY>_<HHMMSS>.cfg
        current_date_time = datetime.now().strftime("%d%m%Y_%H%M%S")
        ftp_filename = f"backupolt_{name}_{current_date_time}.cfg"

        # ── Executa backup configuration ftp ──────────────────────
        backup_command = f"backup configuration ftp {FTP_IP} {ftp_filename}"
        log.info("CMD >> %s", backup_command)
        tn.write(backup_command.encode("ascii") + b"\n")
        time.sleep(2)
        tn.read_very_eager()  # limpa buffer

        # ── Confirmação ────────────────────────────────────────────
        tn.write(b"\n")
        tn.read_until(b"Are you sure to continue? (y/n)", timeout=10)
        tn.write(b"y\n")
        log.info("CMD >> y")

        # ── Aguarda conclusão do upload na OLT ─────────────────────
        log.info("Aguardando %ds para upload FTP concluir...", UPLOAD_WAIT)
        time.sleep(UPLOAD_WAIT)

        # Lê resposta final
        resp = tn.read_very_eager().decode("ascii", errors="ignore")
        if resp.strip():
            log.info("RESP << %s", redact_secrets(resp.strip())[:300])

        # ── Encerra sessão ─────────────────────────────────────────
        tn.write(b"exit\n")
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
        log.exception("Erro no backup Huawei %s", name)
        send_message(f"❌ {progresso} {name} — falha: {exc}")
        return False


def main():
    olts = parse_olts("HUAWEI_OLTS")
    total = len(olts)
    if total == 0:
        send_message("⚠️ Huawei: nenhuma OLT configurada em HUAWEI_OLTS")
        return 1

    ts = datetime.now().strftime("%d/%m/%Y %H:%M")
    send_message(f"🚀 Iniciando backup de {total} OLT(s) Huawei — {ts}")

    ok_list, fail_list = [], []
    for idx, olt in enumerate(olts, start=1):
        prog = f"[{idx}/{total}]"
        if backup_huawei(olt, prog):
            ok_list.append(olt["name"])
        else:
            fail_list.append(olt["name"])
        if idx < total:
            log.info("Aguardando 10s antes da próxima OLT...")
            time.sleep(10)

    resumo = (
        f"📋 Resumo Huawei — {datetime.now().strftime('%d/%m/%Y %H:%M')}\n"
        f"✅ Sucesso ({len(ok_list)}): {', '.join(ok_list) or 'nenhum'}\n"
        f"❌ Falha ({len(fail_list)}): {', '.join(fail_list) or 'nenhum'}"
    )
    send_message(resumo)
    return 1 if fail_list else 0


if __name__ == "__main__":
    sys.exit(main())

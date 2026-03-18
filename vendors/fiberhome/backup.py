#!/usr/bin/env python3
"""Backup de OLTs Fiberhome — Telnet + FTP

Fluxo por OLT:
  1. Conecta via Telnet, faz login.
  2. Executa: upload ftp system <IP> <USER> <PASS> <FILENAME>
  3. Baixa o arquivo do FTP, renomeia com nome da OLT + timestamp.
  4. Envia ao Telegram.
  5. Aguarda 10s antes da próxima OLT.

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

from common.helpers import (
    setup_logging, send_telnet_command,
    ftp_download_rename, cleanup_file,
)
from common.telegram import send_message, send_file
from common.parser import parse_olts

log = setup_logging("fiberhome")

FTP_IP = os.getenv("FTP_IP", "")
FTP_USER = os.getenv("FTP_USER", "")
FTP_PASSWORD = os.getenv("FTP_PASSWORD", "")


def backup_fiberhome(olt: dict, progresso: str) -> bool:
    name = olt["name"]
    ip = olt["ip"]

    send_message(f"🔄 {progresso} Iniciando backup Fiberhome — {name} ({ip})")
    log.info("===== INÍCIO BACKUP FIBERHOME %s (%s) =====", name, ip)

    try:
        tn = telnetlib.Telnet(ip, 23, timeout=20)

        # Login — ajuste os prompts conforme o modelo da OLT
        tn.read_until(b"Login:", timeout=15)
        tn.write(olt["user"].encode("ascii") + b"\n")
        tn.read_until(b"Password:", timeout=15)
        tn.write(olt["password"].encode("ascii") + b"\n")

        time.sleep(3)

        # Nome do arquivo remoto no FTP
        # Formato esperado pela OLT: backupoltfiberhome<DDMMYYYY>.cfg
        ts_file = datetime.now().strftime("%d%m%Y")
        ftp_filename = f"backupoltfiberhome{ts_file}.cfg"

        # Comando correto da OLT Fiberhome:
        # upload ftp system <IP> <USER> <PASS> <FILENAME>
        backup_cmd = (
            f"upload ftp system {FTP_IP} "
            f"{FTP_USER} {FTP_PASSWORD} {ftp_filename}"
        )
        send_telnet_command(tn, backup_cmd, wait_time=10)

        log.info("Aguardando 60s para upload FTP concluir...")
        time.sleep(60)

        tn.write(b"exit\n")
        tn.write(b"exit\n")
        tn.close()

        # Baixar do FTP e renomear
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
            send_message(f"⚠️ {progresso} {name} — backup enviado ao FTP mas falha ao baixar")
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

    ok, fail = [], []
    for idx, olt in enumerate(olts, start=1):
        prog = f"[{idx}/{total}]"
        if backup_fiberhome(olt, prog):
            ok.append(olt["name"])
        else:
            fail.append(olt["name"])
        log.info("Aguardando 10s...")
        time.sleep(10)

    resumo = (
        f"📋 Resumo Fiberhome — {datetime.now().strftime('%d/%m/%Y %H:%M')}\n"
        f"✅ Sucesso ({len(ok)}): {', '.join(ok) or 'nenhum'}\n"
        f"❌ Falha ({len(fail)}): {', '.join(fail) or 'nenhum'}"
    )
    send_message(resumo)


if __name__ == "__main__":
    main()

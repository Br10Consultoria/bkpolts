#!/usr/bin/env python3
"""
Backup de OLTs Parks — Telnet + FTP

Fluxo por OLT:
  1. Conecta via Telnet, aguarda "Press <RETURN>", faz login.
  2. Executa: copy startup-config ftp://<FTP_IP>/<NOME_ARQUIVO> <USER> <PASS>
  3. Baixa o arquivo do FTP, renomeia com nome da OLT + timestamp.
  4. Envia ao Telegram.
  5. Aguarda 10s antes da próxima OLT.

Variáveis de ambiente necessárias:
  PARKS_OLTS — formato NOME:IP:USER:PASS separados por vírgula
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

log = setup_logging("parks")

FTP_IP = os.getenv("FTP_IP", "")
FTP_USER = os.getenv("FTP_USER", "")
FTP_PASSWORD = os.getenv("FTP_PASSWORD", "")


def backup_parks(olt: dict, progresso: str) -> bool:
    name = olt["name"]
    ip = olt["ip"]

    send_message(f"🔄 {progresso} Iniciando backup Parks — {name} ({ip})")
    log.info("===== INÍCIO BACKUP PARKS %s (%s) =====", name, ip)

    try:
        tn = telnetlib.Telnet(ip, 23, timeout=20)

        # Parks exige pressionar ENTER antes do login
        tn.read_until(b"Press <RETURN> to get started", timeout=15)
        tn.write(b"\n")

        tn.read_until(b"Username: ", timeout=15)
        tn.write(olt["user"].encode("ascii") + b"\n")

        tn.read_until(b"Password: ", timeout=15)
        tn.write(olt["password"].encode("ascii") + b"\n")

        time.sleep(3)

        # Nome do arquivo remoto no FTP
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        ftp_filename = f"{name}_backup_{ts}.bin"

        backup_cmd = (
            f"copy startup-config ftp://{FTP_IP}/{ftp_filename} "
            f"{FTP_USER} {FTP_PASSWORD}"
        )
        send_telnet_command(tn, backup_cmd, wait_time=10)

        log.info("Aguardando 30s para upload FTP concluir...")
        time.sleep(30)

        tn.write(b"exit\n")
        tn.close()

        # Baixar do FTP e renomear
        local_file = ftp_download_rename(
            FTP_IP, FTP_USER, FTP_PASSWORD,
            ftp_filename, name, extension="bin"
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
        log.exception("Erro no backup Parks %s", name)
        send_message(f"❌ {progresso} {name} — falha: {exc}")
        return False


def main():
    olts = parse_olts("PARKS_OLTS")
    total = len(olts)
    if total == 0:
        send_message("⚠️ Parks: nenhuma OLT configurada em PARKS_OLTS")
        return

    ts = datetime.now().strftime("%d/%m/%Y %H:%M")
    send_message(f"🚀 Iniciando backup de {total} OLT(s) Parks — {ts}")

    ok, fail = [], []
    for idx, olt in enumerate(olts, start=1):
        prog = f"[{idx}/{total}]"
        if backup_parks(olt, prog):
            ok.append(olt["name"])
        else:
            fail.append(olt["name"])
        log.info("Aguardando 10s...")
        time.sleep(10)

    resumo = (
        f"📋 Resumo Parks — {datetime.now().strftime('%d/%m/%Y %H:%M')}\n"
        f"✅ Sucesso ({len(ok)}): {', '.join(ok) or 'nenhum'}\n"
        f"❌ Falha ({len(fail)}): {', '.join(fail) or 'nenhum'}"
    )
    send_message(resumo)


if __name__ == "__main__":
    main()

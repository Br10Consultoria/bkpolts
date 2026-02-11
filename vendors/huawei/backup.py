#!/usr/bin/env python3
"""
Backup de OLTs Huawei — Telnet + FTP

Fluxo por OLT:
  1. Conecta via Telnet, faz login.
  2. Executa: backup configuration ftp <FTP_IP> <USER> <PASS> <FILENAME>
  3. Baixa o arquivo do FTP, renomeia com nome da OLT + timestamp.
  4. Envia ao Telegram.
  5. Aguarda 10s antes da próxima OLT.

IMPORTANTE: O comando de backup pode variar conforme o modelo/firmware
da OLT Huawei. Ajuste a função backup_huawei() conforme necessário.

Variáveis de ambiente necessárias:
  HUAWEI_OLTS — formato NOME:IP:USER:PASS separados por vírgula
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

log = setup_logging("huawei")

FTP_IP = os.getenv("FTP_IP", "")
FTP_USER = os.getenv("FTP_USER", "")
FTP_PASSWORD = os.getenv("FTP_PASSWORD", "")


def backup_huawei(olt: dict, progresso: str) -> bool:
    name = olt["name"]
    ip = olt["ip"]

    send_message(f"🔄 {progresso} Iniciando backup Huawei — {name} ({ip})")
    log.info("===== INÍCIO BACKUP HUAWEI %s (%s) =====", name, ip)

    try:
        tn = telnetlib.Telnet(ip, 23, timeout=20)

        # Login — Huawei costuma usar >>User name: e >>User password:
        tn.read_until(b"name:", timeout=15)
        tn.write(olt["user"].encode("ascii") + b"\n")
        tn.read_until(b"password:", timeout=15)
        tn.write(olt["password"].encode("ascii") + b"\n")

        time.sleep(3)

        # Entrar no modo enable
        send_telnet_command(tn, "enable")

        # Nome do arquivo remoto no FTP
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        ftp_filename = f"{name}_backup_{ts}.cfg"

        # ============================================================
        # AJUSTE ESTE COMANDO conforme o modelo/firmware da sua OLT
        # Exemplos comuns Huawei:
        #   backup configuration to-file ftp://<USER>:<PASS>@<IP>/<FILE>
        #   save
        #   copy flash:/startup.cfg ftp://<USER>:<PASS>@<IP>/<FILE>
        # ============================================================
        backup_cmd = (
            f"backup configuration to-file "
            f"ftp://{FTP_USER}:{FTP_PASSWORD}@{FTP_IP}/{ftp_filename}"
        )
        send_telnet_command(tn, backup_cmd, wait_time=10)

        log.info("Aguardando 60s para upload FTP concluir...")
        time.sleep(60)

        tn.write(b"quit\n")
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
        log.exception("Erro no backup Huawei %s", name)
        send_message(f"❌ {progresso} {name} — falha: {exc}")
        return False


def main():
    olts = parse_olts("HUAWEI_OLTS")
    total = len(olts)
    if total == 0:
        send_message("⚠️ Huawei: nenhuma OLT configurada em HUAWEI_OLTS")
        return

    ts = datetime.now().strftime("%d/%m/%Y %H:%M")
    send_message(f"🚀 Iniciando backup de {total} OLT(s) Huawei — {ts}")

    ok, fail = [], []
    for idx, olt in enumerate(olts, start=1):
        prog = f"[{idx}/{total}]"
        if backup_huawei(olt, prog):
            ok.append(olt["name"])
        else:
            fail.append(olt["name"])
        log.info("Aguardando 10s...")
        time.sleep(10)

    resumo = (
        f"📋 Resumo Huawei — {datetime.now().strftime('%d/%m/%Y %H:%M')}\n"
        f"✅ Sucesso ({len(ok)}): {', '.join(ok) or 'nenhum'}\n"
        f"❌ Falha ({len(fail)}): {', '.join(fail) or 'nenhum'}"
    )
    send_message(resumo)


if __name__ == "__main__":
    main()

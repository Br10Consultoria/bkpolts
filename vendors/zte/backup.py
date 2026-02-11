#!/usr/bin/env python3
"""
Backup de OLTs ZTE — Telnet + FTP

Dois tipos de OLT:
  - ZTE padrão (ZTE_OLTS):
      Comando: file upload cfg-startup startrun.dat ftp ipaddress <IP> user <U> password <P>
  - ZTE Titan (ZTE_TITAN_OLTS):
      Comando: copy ftp root: /datadisk0/DATA0/startrun.dat //<IP>/startrun.dat@<U>:<P>

Ambos geram o mesmo arquivo "startrun.dat" no FTP. Após o backup,
o script baixa o startrun.dat do FTP, renomeia com o nome da OLT
(ex: zte_aramari_20260211_130000.dat) e envia ao Telegram.

Variáveis de ambiente necessárias:
  ZTE_OLTS       — OLTs ZTE padrão (NOME:IP:USER:PASS, ...)
  ZTE_TITAN_OLTS — OLTs ZTE Titan  (NOME:IP:USER:PASS, ...)
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

log = setup_logging("zte")

FTP_IP = os.getenv("FTP_IP", "")
FTP_USER = os.getenv("FTP_USER", "")
FTP_PASSWORD = os.getenv("FTP_PASSWORD", "")


# ============================================================
# ZTE padrão
# ============================================================

def backup_zte(olt: dict, progresso: str) -> bool:
    name = olt["name"]
    ip = olt["ip"]

    send_message(f"🔄 {progresso} Iniciando backup ZTE — {name} ({ip})")
    log.info("===== INÍCIO BACKUP ZTE %s (%s) =====", name, ip)

    try:
        tn = telnetlib.Telnet(ip, 23, timeout=20)

        tn.read_until(b"login:", timeout=15)
        tn.write(olt["user"].encode("ascii") + b"\n")
        tn.read_until(b"Password:", timeout=15)
        tn.write(olt["password"].encode("ascii") + b"\n")

        time.sleep(3)
        send_telnet_command(tn, "configure terminal")

        ftp_cmd = (
            f"file upload cfg-startup startrun.dat ftp ipaddress {FTP_IP} "
            f"user {FTP_USER} password {FTP_PASSWORD}"
        )
        send_telnet_command(tn, ftp_cmd, wait_time=5)

        log.info("Aguardando 60s para upload FTP concluir...")
        time.sleep(60)

        tn.write(b"exit\n")
        tn.close()

        # Baixar do FTP e renomear
        local_file = ftp_download_rename(
            FTP_IP, FTP_USER, FTP_PASSWORD,
            "startrun.dat", name, extension="dat"
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
        log.exception("Erro no backup ZTE %s", name)
        send_message(f"❌ {progresso} {name} — falha: {exc}")
        return False


# ============================================================
# ZTE Titan
# ============================================================

def backup_zte_titan(olt: dict, progresso: str) -> bool:
    name = olt["name"]
    ip = olt["ip"]

    send_message(f"🔄 {progresso} Iniciando backup ZTE Titan — {name} ({ip})")
    log.info("===== INÍCIO BACKUP ZTE TITAN %s (%s) =====", name, ip)

    try:
        tn = telnetlib.Telnet(ip, 23, timeout=20)

        tn.read_until(b"login:", timeout=15)
        tn.write(olt["user"].encode("ascii") + b"\n")
        tn.read_until(b"Password:", timeout=15)
        tn.write(olt["password"].encode("ascii") + b"\n")

        time.sleep(3)

        backup_cmd = (
            f"copy ftp root: /datadisk0/DATA0/startrun.dat "
            f"//{FTP_IP}/startrun.dat@{FTP_USER}:{FTP_PASSWORD}"
        )
        send_telnet_command(tn, backup_cmd, wait_time=10)

        log.info("Aguardando 60s para conclusão do backup...")
        time.sleep(60)

        tn.write(b"exit\n")
        tn.close()

        # Baixar do FTP e renomear
        local_file = ftp_download_rename(
            FTP_IP, FTP_USER, FTP_PASSWORD,
            "startrun.dat", name, extension="dat"
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
        log.exception("Erro no backup ZTE Titan %s", name)
        send_message(f"❌ {progresso} {name} — falha: {exc}")
        return False


# ============================================================
# Main
# ============================================================

def main():
    olts_padrao = parse_olts("ZTE_OLTS")
    olts_titan = parse_olts("ZTE_TITAN_OLTS")

    todas = [(olt, "zte") for olt in olts_padrao] + [(olt, "titan") for olt in olts_titan]
    total = len(todas)

    if total == 0:
        send_message("⚠️ ZTE: nenhuma OLT configurada em ZTE_OLTS / ZTE_TITAN_OLTS")
        return

    ts = datetime.now().strftime("%d/%m/%Y %H:%M")
    send_message(f"🚀 Iniciando backup de {total} OLT(s) ZTE — {ts}")

    ok, fail = [], []
    for idx, (olt, tipo) in enumerate(todas, start=1):
        prog = f"[{idx}/{total}]"
        if tipo == "titan":
            sucesso = backup_zte_titan(olt, prog)
        else:
            sucesso = backup_zte(olt, prog)

        if sucesso:
            ok.append(olt["name"])
        else:
            fail.append(olt["name"])

        log.info("Aguardando 10s...")
        time.sleep(10)

    resumo = (
        f"📋 Resumo ZTE — {datetime.now().strftime('%d/%m/%Y %H:%M')}\n"
        f"✅ Sucesso ({len(ok)}): {', '.join(ok) or 'nenhum'}\n"
        f"❌ Falha ({len(fail)}): {', '.join(fail) or 'nenhum'}"
    )
    send_message(resumo)


if __name__ == "__main__":
    main()

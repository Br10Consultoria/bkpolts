#!/usr/bin/env python3
"""Backup de OLTs Huawei — Telnet + FTP

Fluxo por OLT (baseado na sessão real):
  1. Conecta via Telnet, aguarda "username:"
  2. Envia usuário, aguarda "password:", envia senha
  3. Aguarda prompt "#" (já entra direto no modo privilegiado)
  4. Monta o nome do arquivo: backupolt<NOME><DDMMYY>.cfg
  5. Executa o comando de backup:
       backup configuration ftp <FTP_IP> <FILENAME>
  6. Aguarda prompt de confirmação "(y/n)" e envia "y"
  7. Aguarda 30s para o upload FTP concluir na OLT
  8. Envia "quit" e fecha a sessão
  9. Baixa o arquivo do FTP e envia ao Telegram

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

from common.helpers import ftp_download_rename, cleanup_file, setup_logging
from common.telegram import send_message, send_file
from common.parser import parse_olts

log = setup_logging("huawei")

FTP_IP       = os.getenv("FTP_IP", "")
FTP_USER     = os.getenv("FTP_USER", "")
FTP_PASSWORD = os.getenv("FTP_PASSWORD", "")

TIMEOUT      = 20   # timeout geral de leitura de prompts (segundos)
UPLOAD_WAIT  = 30   # segundos aguardando o upload FTP concluir na OLT


def write(tn: telnetlib.Telnet, cmd: str):
    """Envia um comando + newline e loga."""
    log.info("CMD >> %s", cmd if "password" not in cmd.lower() else "****")
    tn.write(cmd.encode("ascii") + b"\n")


def read_until(tn: telnetlib.Telnet, expected: bytes, timeout: int = TIMEOUT) -> str:
    """Aguarda um prompt e retorna o texto recebido."""
    data = tn.read_until(expected, timeout=timeout).decode("ascii", errors="ignore")
    log.info("RESP << %s", data.strip()[:300])
    return data


def backup_huawei(olt: dict, progresso: str) -> bool:
    name     = olt["name"]
    ip       = olt["ip"]
    user     = olt["user"]
    password = olt["password"]

    send_message(f"🔄 {progresso} Iniciando backup Huawei — {name} ({ip})")
    log.info("===== INÍCIO BACKUP HUAWEI %s (%s) =====", name, ip)

    try:
        tn = telnetlib.Telnet(ip, 23, timeout=TIMEOUT)

        # ── Login ──────────────────────────────────────────────────
        # Huawei: "username:" (case insensitive, pode vir como "User name:")
        data = tn.read_until(b":", timeout=TIMEOUT).decode("ascii", errors="ignore")
        log.info("RESP << %s", data.strip()[:200])
        write(tn, user)

        read_until(tn, b"password:")
        write(tn, password)

        # ── Aguarda prompt # (modo privilegiado direto) ────────────
        # Huawei entra direto no modo Admin após login, sem "enable" extra
        read_until(tn, b"#")

        # ── Monta nome do arquivo ──────────────────────────────────
        # Formato: backupolt<NOME><DDMMYY>.cfg  ex: backupoltcosme190326.cfg
        ts_file = datetime.now().strftime("%d%m%y")
        nome_lower = name.lower()
        ftp_filename = f"backupolt{nome_lower}{ts_file}.cfg"

        # ── Executa backup configuration ftp ──────────────────────
        # Comando: backup configuration ftp <IP> <FILENAME>
        # (sem usuário/senha no comando — a OLT usa as credenciais FTP
        #  configuradas internamente ou aceita anônimo conforme o modelo)
        backup_cmd = f"backup configuration ftp {FTP_IP} {ftp_filename}"
        write(tn, backup_cmd)

        # ── Aguarda confirmação "(y/n)" e confirma com "y" ─────────
        resp = read_until(tn, b"(y/n)", timeout=TIMEOUT)
        write(tn, "y")

        # ── Aguarda conclusão do upload na OLT ─────────────────────
        log.info("Aguardando %ds para upload FTP concluir...", UPLOAD_WAIT)
        time.sleep(UPLOAD_WAIT)

        # Lê resposta final
        resp = tn.read_very_eager().decode("ascii", errors="ignore")
        if resp.strip():
            log.info("RESP << %s", resp.strip()[:300])

        # ── Encerra sessão ─────────────────────────────────────────
        write(tn, "quit")
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
        return

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


if __name__ == "__main__":
    main()

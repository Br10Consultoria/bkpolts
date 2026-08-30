#!/usr/bin/env python3
"""
Backup de OLTs Datacom (DM4615, DM4618 e demais DmOS) — Telnet + TFTP

Fluxo por OLT (confirmado contra sessão real de produção):
  1. Conecta via Telnet, faz login.
  2. Salva o running-config com nome único, direto no prompt exec (sem
     entrar em "config"): `show running-config | save overwrite <arquivo>`.
  3. Envia o arquivo para o servidor TFTP (serviço "tftp" deste mesmo
     docker-compose — ver README, seção "Servidor de backup Datacom"):
     `copy file <arquivo> tftp://<TFTP_IP>`.
  4. Aguarda o arquivo chegar no diretório local (/app/backups), que é o
     mesmo diretório onde o container tftp escreve (mesmo volume).
  5. Envia o arquivo ao Telegram.
  6. Aguarda 10s antes da próxima OLT.

Variáveis de ambiente necessárias:
  DATACOM_OLTS  — formato NOME:IP:USER:PASS separados por vírgula
  TFTP_IP       — IP do servidor TFTP (o serviço "tftp" deste projeto,
                   rodando com network_mode: host — normalmente o IP
                   deste mesmo servidor)
"""

import os
import re
import sys
import time
import telnetlib
from datetime import datetime

sys.path.insert(0, "/app")

from common.helpers import setup_logging, send_telnet_command, cleanup_file
from common.telegram import send_message, send_file
from common.parser import parse_olts

log = setup_logging("datacom")

TFTP_IP = os.getenv("TFTP_IP", "")
BACKUP_DIR = "/app/backups"


def backup_datacom(olt: dict, progresso: str) -> bool:
    name = olt["name"]
    ip = olt["ip"]

    send_message(f"🔄 {progresso} Iniciando backup Datacom — {name} ({ip})")
    log.info("===== INÍCIO BACKUP %s (%s) =====", name, ip)

    try:
        tn = telnetlib.Telnet(ip, 23, timeout=20)

        tn.read_until(b"login:", timeout=15)
        tn.write(olt["user"].encode("ascii") + b"\n")
        tn.read_until(b"Password:", timeout=15)
        tn.write(olt["password"].encode("ascii") + b"\n")

        tn.read_until(b"Welcome to the DmOS CLI", timeout=20)
        log.info("Login OK")

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        # A CLI da OLT quebra o comando `save` em tokens separados por espaço
        # (e possivelmente outros caracteres especiais) — um nome de OLT como
        # "PEDRO BRAGA NOVA" vira "syntax error: element does not exist".
        # Sanitiza para um nome de arquivo seguro independente do nome exibido.
        safe_name = re.sub(r"[^A-Za-z0-9_-]", "_", name)
        filename = f"backup_{safe_name}_{ts}.txt"

        # Salvar backup na OLT — direto no prompt exec (sem entrar em "config").
        send_telnet_command(tn, f"show running-config | save overwrite {filename}")
        log.info("Aguardando 10s para gravação interna...")
        time.sleep(10)

        # Enviar para o TFTP
        send_telnet_command(tn, f"copy file {filename} tftp://{TFTP_IP}", wait_time=30)

        tn.write(b"exit\n")
        tn.close()

        # Aguardar arquivo chegar (mesmo volume que o container tftp escreve)
        local_file = os.path.join(BACKUP_DIR, filename)
        last_size = -1
        stable = 0

        for i in range(90):
            if os.path.exists(local_file):
                size = os.path.getsize(local_file)
                log.info("TFTP recebendo (%ds): %d bytes", i * 2, size)
                if size == last_size and size > 0:
                    stable += 1
                else:
                    stable = 0
                last_size = size
                if stable >= 5:
                    send_file(local_file, caption=f"📦 Backup {name} — {filename}")
                    send_message(f"✅ {progresso} {name} — backup concluído")
                    cleanup_file(local_file)
                    return True
            time.sleep(2)

        send_message(
            f"⚠️ {progresso} {name} — comando de cópia enviado mas o arquivo não "
            f"chegou em {BACKUP_DIR}. Verifique se o container 'tftp' está no ar "
            f"e se TFTP_IP aponta para ele."
        )
        return False

    except Exception as exc:
        log.exception("Erro no backup %s", name)
        send_message(f"❌ {progresso} {name} — falha: {exc}")
        return False


def main():
    olts = parse_olts("DATACOM_OLTS")
    total = len(olts)
    if total == 0:
        send_message("⚠️ Datacom: nenhuma OLT configurada em DATACOM_OLTS")
        return

    if not TFTP_IP:
        send_message(
            "⚠️ Datacom: TFTP_IP não configurado no .env — veja o README "
            "(seção 'Servidor de backup Datacom')."
        )
        return

    ts = datetime.now().strftime("%d/%m/%Y %H:%M")
    send_message(f"🚀 Iniciando backup de {total} OLT(s) Datacom — {ts}")

    ok, fail = [], []
    for idx, olt in enumerate(olts, start=1):
        prog = f"[{idx}/{total}]"
        if backup_datacom(olt, prog):
            ok.append(olt["name"])
        else:
            fail.append(olt["name"])
        log.info("Aguardando 10s...")
        time.sleep(10)

    resumo = (
        f"📋 Resumo Datacom — {datetime.now().strftime('%d/%m/%Y %H:%M')}\n"
        f"✅ Sucesso ({len(ok)}): {', '.join(ok) or 'nenhum'}\n"
        f"❌ Falha ({len(fail)}): {', '.join(fail) or 'nenhum'}"
    )
    send_message(resumo)


if __name__ == "__main__":
    main()

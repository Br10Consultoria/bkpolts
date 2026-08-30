#!/usr/bin/env python3
"""
Backup de OLTs Datacom (DM4615, DM4618 e demais DmOS) — Telnet + SFTP/SCP

Fluxo por OLT:
  1. Conecta via Telnet, faz login, entra em config.
  2. Salva backup com nome único (backup_NOME_TIMESTAMP.txt).
  3. A própria OLT envia o arquivo via SFTP/SCP para um servidor SSH
     dedicado (ver README, seção "Servidor de backup Datacom").
  4. Aguarda o arquivo chegar no diretório local (/app/backups), que é o
     mesmo diretório onde o usuário SFTP do host grava (bind mount).
  5. Envia o arquivo ao Telegram.
  6. Aguarda 10s antes da próxima OLT.

ATENÇÃO — verifique antes de usar em produção:
  O comando de destino usado abaixo (`copy file <arquivo> {scheme}://...`)
  assume que o firmware DmOS aceita o esquema configurado em
  DATACOM_COPY_SCHEME (padrão "sftp"). Isso NÃO foi confirmado contra o
  manual/firmware específico das OLTs 4615/4618 em uso. Antes do primeiro
  uso real, conecte via telnet em uma OLT, entre em "config" e rode:

      copy ?

  Isso lista os esquemas de destino aceitos (tftp:, ftp:, sftp:, scp: etc.).
  Se o correto for "scp" em vez de "sftp", basta ajustar
  DATACOM_COPY_SCHEME=scp no .env — nenhum código precisa mudar.

Variáveis de ambiente necessárias:
  DATACOM_OLTS           — formato NOME:IP:USER:PASS separados por vírgula
  DATACOM_BACKUP_HOST    — IP do servidor SSH que recebe os backups
  DATACOM_BACKUP_USER    — usuário SFTP/SCP dedicado (ver README)
  DATACOM_BACKUP_PASSWORD— senha desse usuário
  DATACOM_BACKUP_PATH    — caminho remoto (relativo ao chroot) onde salvar,
                            padrão "" (raiz do chroot)
  DATACOM_COPY_SCHEME    — "sftp" (padrão) ou "scp", conforme confirmado
                            no `copy ?` da OLT
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

BACKUP_HOST = os.getenv("DATACOM_BACKUP_HOST", "")
BACKUP_USER = os.getenv("DATACOM_BACKUP_USER", "")
BACKUP_PASSWORD = os.getenv("DATACOM_BACKUP_PASSWORD", "")
BACKUP_REMOTE_PATH = os.getenv("DATACOM_BACKUP_PATH", "").strip("/")
COPY_SCHEME = os.getenv("DATACOM_COPY_SCHEME", "sftp").strip().lower()
BACKUP_DIR = "/app/backups"


def _build_copy_destination(filename: str) -> str:
    """Monta a URL de destino do comando `copy` conforme DATACOM_COPY_SCHEME."""
    remote_path = f"{BACKUP_REMOTE_PATH}/{filename}" if BACKUP_REMOTE_PATH else filename
    return f"{COPY_SCHEME}://{BACKUP_USER}:{BACKUP_PASSWORD}@{BACKUP_HOST}/{remote_path}"


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

        send_telnet_command(tn, "config")

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        # A CLI da OLT quebra o comando `save` em tokens separados por espaço
        # (e possivelmente outros caracteres especiais) — um nome de OLT como
        # "PEDRO BRAGA NOVA" vira "syntax error: element does not exist".
        # Sanitiza para um nome de arquivo seguro independente do nome exibido.
        safe_name = re.sub(r"[^A-Za-z0-9_-]", "_", name)
        filename = f"backup_{safe_name}_{ts}.txt"

        # Salvar backup na OLT
        send_telnet_command(tn, f"save {filename}")
        log.info("Aguardando 90s para gravação interna...")
        time.sleep(90)

        # Enviar via SFTP/SCP para o servidor de backup dedicado.
        # Não usa send_telnet_command aqui de propósito: aquele helper loga o
        # comando inteiro, e este comando embute a senha na URL de destino.
        destination = _build_copy_destination(filename)
        log.info("CMD >> copy file %s %s://%s:****@%s/...", filename, COPY_SCHEME, BACKUP_USER, BACKUP_HOST)
        tn.write(f"copy file {filename} {destination}".encode("ascii") + b"\n")
        time.sleep(90)
        response = tn.read_very_eager().decode("ascii", errors="replace")
        if response.strip():
            log.info("RESP << %s", response.strip()[:500])

        tn.write(b"exit\n")
        tn.close()

        # Aguardar arquivo chegar (bind mount compartilhado com o host SSH)
        local_file = os.path.join(BACKUP_DIR, filename)
        last_size = -1
        stable = 0

        for i in range(90):
            if os.path.exists(local_file):
                size = os.path.getsize(local_file)
                log.info("Recebendo via %s (%ds): %d bytes", COPY_SCHEME, i * 2, size)
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
            f"chegou em {BACKUP_DIR}. Verifique o usuário/host SSH de backup e "
            f"se DATACOM_COPY_SCHEME corresponde ao suportado pela OLT (`copy ?`)."
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

    if not BACKUP_HOST or not BACKUP_USER:
        send_message(
            "⚠️ Datacom: DATACOM_BACKUP_HOST/DATACOM_BACKUP_USER não configurados "
            "no .env — veja o README (seção 'Servidor de backup Datacom')."
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

#!/usr/bin/env python3
"""Backup de OLTs Intelbras G16 — Telnet + FTP/TFTP

Fluxo por OLT:
  1. Conecta via Telnet, aguarda "Username:" ou "login:"
  2. Envia usuário, aguarda "Password:", envia senha
  3. Aguarda prompt "GPON#" (modo privilegiado direto)
  4. Executa o backup de duas formas (configurável via INTELBRAS_BACKUP_METHOD):
     - Método "ftp"  : upload configuration ftp inet <FTP_IP> <FILENAME>
     - Método "tftp" : upload configuration tftp inet <TFTP_IP> <FILENAME>
     - Método "local": copy running-config startup-config (salva localmente)
  5. Aguarda confirmação de sucesso
  6. Envia "exit" e fecha a sessão
  7. Baixa o arquivo do FTP/TFTP e envia ao Telegram (quando aplicável)

Variáveis de ambiente necessárias:
  INTELBRAS_G16_OLTS      — formato NOME:IP:USER:PASS separados por vírgula
  INTELBRAS_BACKUP_METHOD — "ftp" (padrão), "tftp" ou "local"
  FTP_IP, FTP_USER, FTP_PASSWORD  (para método ftp)
  TFTP_IP                          (para método tftp)
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

log = setup_logging("intelbras_g16")

FTP_IP       = os.getenv("FTP_IP", "")
FTP_USER     = os.getenv("FTP_USER", "")
FTP_PASSWORD = os.getenv("FTP_PASSWORD", "")
TFTP_IP      = os.getenv("TFTP_IP", "")
METHOD       = os.getenv("INTELBRAS_BACKUP_METHOD", "ftp").lower()  # ftp | tftp | local

UPLOAD_WAIT  = 30   # segundos aguardando o upload concluir na OLT


def _send_cmd(tn: telnetlib.Telnet, cmd: str, wait: float = 1.0):
    """Envia um comando e aguarda um breve delay."""
    tn.write(cmd.encode("ascii") + b"\n")
    log.info("CMD >> %s", redact_secrets(cmd))
    time.sleep(wait)


def backup_intelbras_g16(olt: dict, progresso: str) -> bool:
    name     = olt["name"]
    ip       = olt["ip"]
    user     = olt["user"]
    password = olt["password"]

    send_message(f"🔄 {progresso} Iniciando backup Intelbras G16 — {name} ({ip})")
    log.info("===== INÍCIO BACKUP INTELBRAS G16 %s (%s) =====", name, ip)

    try:
        tn = telnetlib.Telnet(ip, 23, timeout=20)

        # ── Login ──────────────────────────────────────────────────
        # A G16 pode exibir "Username:" ou "login:"
        idx, _, _ = tn.expect([b"Username:", b"username:", b"login:"], timeout=15)
        if idx < 0:
            raise TimeoutError("Prompt de login não encontrado")
        _send_cmd(tn, user)

        tn.read_until(b"Password:", timeout=10)
        _send_cmd(tn, password)

        # ── Aguarda prompt GPON# ───────────────────────────────────
        resp = tn.read_until(b"GPON#", timeout=15).decode("ascii", errors="ignore")
        if "GPON#" not in resp:
            raise TimeoutError("Prompt 'GPON#' não encontrado após login")
        log.info("Prompt GPON# obtido — modo privilegiado ativo")

        # ── Monta nome do arquivo ──────────────────────────────────
        current_date_time = datetime.now().strftime("%d%m%Y_%H%M%S")
        ftp_filename = f"backupolt_{name}_{current_date_time}.cfg"

        # ── Executa o backup conforme o método configurado ─────────
        if METHOD == "local":
            # Salva running-config como startup-config (persiste no flash)
            log.info("Método: local (copy running-config startup-config)")
            _send_cmd(tn, "copy running-config startup-config", wait=5)
            resp = tn.read_very_eager().decode("ascii", errors="ignore")
            log.info("RESP << %s", redact_secrets(resp.strip())[:300])
            send_message(f"✅ {progresso} {name} — configuração salva localmente (startup-config)")
            tn.write(b"exit\n")
            tn.close()
            return True

        elif METHOD == "tftp":
            # upload configuration tftp inet <TFTP_IP> <FILENAME>
            if not TFTP_IP:
                raise ValueError("TFTP_IP não configurado no .env")
            backup_cmd = f"upload configuration tftp inet {TFTP_IP} {ftp_filename}"
            log.info("Método: TFTP — %s", backup_cmd)
            _send_cmd(tn, backup_cmd, wait=3)

        else:
            # upload configuration ftp inet <FTP_IP> <FILENAME>  (padrão)
            if not FTP_IP:
                raise ValueError("FTP_IP não configurado no .env")
            backup_cmd = f"upload configuration ftp inet {FTP_IP} {ftp_filename}"
            log.info("Método: FTP — %s", backup_cmd)
            _send_cmd(tn, backup_cmd, wait=3)

        # ── Aguarda conclusão do upload ────────────────────────────
        log.info("Aguardando %ds para upload concluir...", UPLOAD_WAIT)
        time.sleep(UPLOAD_WAIT)

        resp = tn.read_very_eager().decode("ascii", errors="ignore")
        if resp.strip():
            log.info("RESP << %s", redact_secrets(resp.strip())[:300])

        # ── Encerra sessão ─────────────────────────────────────────
        tn.write(b"exit\n")
        tn.close()

        # ── Baixa do FTP/TFTP e envia ao Telegram ─────────────────
        if METHOD == "ftp":
            local_file = ftp_download_rename(
                FTP_IP, FTP_USER, FTP_PASSWORD,
                ftp_filename, name, extension="cfg"
            )
        else:
            # TFTP: download via tftp local (se disponível)
            import subprocess
            local_path = f"/tmp/{ftp_filename}"
            result = subprocess.run(
                ["tftp", "-g", "-r", ftp_filename, "-l", local_path, TFTP_IP],
                capture_output=True, timeout=30
            )
            local_file = local_path if result.returncode == 0 else None

        if local_file:
            fname = os.path.basename(local_file)
            send_file(local_file, caption=f"📦 Backup {name} — {fname}")
            send_message(f"✅ {progresso} {name} — backup concluído")
            cleanup_file(local_file)
            return True
        else:
            send_message(
                f"⚠️ {progresso} {name} — upload enviado mas falha ao baixar do "
                f"{'FTP' if METHOD == 'ftp' else 'TFTP'}"
            )
            return False

    except Exception as exc:
        log.exception("Erro no backup Intelbras G16 %s", name)
        send_message(f"❌ {progresso} {name} — falha: {exc}")
        return False


def main():
    olts = parse_olts("INTELBRAS_G16_OLTS")
    total = len(olts)
    if total == 0:
        send_message("⚠️ Intelbras G16: nenhuma OLT configurada em INTELBRAS_G16_OLTS")
        return 1

    ts = datetime.now().strftime("%d/%m/%Y %H:%M")
    send_message(
        f"🚀 Iniciando backup de {total} OLT(s) Intelbras G16 — {ts} "
        f"[método: {METHOD.upper()}]"
    )

    ok_list, fail_list = [], []
    for idx, olt in enumerate(olts, start=1):
        prog = f"[{idx}/{total}]"
        if backup_intelbras_g16(olt, prog):
            ok_list.append(olt["name"])
        else:
            fail_list.append(olt["name"])
        if idx < total:
            log.info("Aguardando 10s antes da próxima OLT...")
            time.sleep(10)

    resumo = (
        f"📋 Resumo Intelbras G16 — {datetime.now().strftime('%d/%m/%Y %H:%M')}\n"
        f"✅ Sucesso ({len(ok_list)}): {', '.join(ok_list) or 'nenhum'}\n"
        f"❌ Falha ({len(fail_list)}): {', '.join(fail_list) or 'nenhum'}"
    )
    send_message(resumo)
    return 1 if fail_list else 0


if __name__ == "__main__":
    sys.exit(main())

"""
Funções utilitárias compartilhadas por todos os scripts de backup.
"""

import os
import sys
import time
import logging
import ftplib
import re
from datetime import datetime


def redact_secrets(value: str) -> str:
    """Remove senhas conhecidas de comandos antes de gravá-los em log."""
    redacted = value
    for key, secret in os.environ.items():
        if ("PASS" in key.upper() or "TOKEN" in key.upper() or "SECRET" in key.upper()) and secret:
            redacted = redacted.replace(secret, "****")
    redacted = re.sub(r"(?i)(password\s+)\S+", r"\1****", redacted)
    redacted = re.sub(r"(//[^/@:]+:)[^@]+(@)", r"\1****\2", redacted)
    return redacted


def setup_logging(vendor_name: str):
    """Configura logging padronizado para qualquer vendor."""
    log_dir = "/app/logs"
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, f"backup_{vendor_name}.log")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(sys.stdout),
        ],
    )
    return logging.getLogger("olt-backup")


def send_telnet_command(tn, command: str, wait_time: int = 2) -> str:
    """Envia um comando via Telnet e retorna a resposta."""
    log = logging.getLogger("olt-backup")
    log.info("CMD >> %s", redact_secrets(command))
    tn.write(command.encode("ascii") + b"\n")
    time.sleep(wait_time)
    response = tn.read_very_eager().decode("ascii", errors="replace")
    if response.strip():
        log.info("RESP << %s", redact_secrets(response.strip())[:500])
    return response


def ftp_download_rename(ftp_ip: str, ftp_user: str, ftp_pass: str,
                        remote_file: str, olt_name: str,
                        extension: str = "dat") -> str | None:
    """
    Conecta ao FTP, baixa um arquivo remoto, renomeia com o nome
    da OLT + timestamp e salva em /app/backups/.
    Retorna o caminho local do arquivo ou None em caso de erro.
    """
    log = logging.getLogger("olt-backup")
    backup_dir = "/app/backups"
    os.makedirs(backup_dir, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    new_name = f"{olt_name.lower()}_{ts}.{extension}"
    local_path = os.path.join(backup_dir, new_name)

    try:
        log.info("FTP: baixando %s de %s ...", remote_file, ftp_ip)
        ftp = ftplib.FTP(ftp_ip, timeout=30)
        ftp.login(user=ftp_user, passwd=ftp_pass)
        with open(local_path, "wb") as f:
            ftp.retrbinary(f"RETR {remote_file}", f.write)
        ftp.quit()
        log.info("FTP: salvo como %s", new_name)
        return local_path
    except Exception as exc:
        log.error("FTP erro ao baixar %s: %s", remote_file, exc)
        return None


def cleanup_file(filepath: str):
    """Remove um arquivo local após envio."""
    log = logging.getLogger("olt-backup")
    try:
        if filepath and os.path.isfile(filepath):
            os.remove(filepath)
            log.info("Arquivo removido: %s", filepath)
    except Exception as exc:
        log.error("Erro ao remover %s: %s", filepath, exc)

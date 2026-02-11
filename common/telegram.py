"""
Módulo compartilhado de envio de mensagens e arquivos ao Telegram.
Usado por todos os scripts de backup de vendors.
"""

import os
import logging
import requests

log = logging.getLogger("olt-backup")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")


def send_message(text: str):
    """Envia uma mensagem de texto para o chat do Telegram."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        log.warning("Telegram não configurado. Mensagem não enviada.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
    try:
        resp = requests.post(url, data=data, timeout=30)
        if resp.status_code == 200:
            log.info("Telegram MSG enviada.")
        else:
            log.error("Erro Telegram MSG: %s", resp.text)
    except Exception as exc:
        log.error("Exceção Telegram MSG: %s", exc)


def send_file(filepath: str, caption: str = ""):
    """Envia um arquivo para o chat do Telegram com legenda opcional."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        log.warning("Telegram não configurado. Arquivo não enviado.")
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendDocument"
    data = {"chat_id": TELEGRAM_CHAT_ID}
    if caption:
        data["caption"] = caption
    try:
        with open(filepath, "rb") as f:
            resp = requests.post(url, data=data, files={"document": f}, timeout=120)
        if resp.status_code == 200:
            log.info("Telegram FILE enviado: %s", filepath)
            return True
        else:
            log.error("Erro Telegram FILE %s: %s", filepath, resp.text)
            return False
    except Exception as exc:
        log.error("Exceção Telegram FILE %s: %s", filepath, exc)
        return False

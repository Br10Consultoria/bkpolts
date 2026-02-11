#!/usr/bin/env python3
import telnetlib
import time
import os
import requests
import logging
from datetime import datetime

# =========================================================
# CONFIGURAÇÕES
# =========================================================
OLTS = {
    "DC1": {
        "ip": "172.24.25.2",
        "user": "backupolt",
        "password": "B3ni0808@#$"
    },
    "DC2": {
        "ip": "172.24.25.6",
        "user": "backupolt",
        "password": "B3ni0808@#$"
    }
}

TFTP_HOST = "10.50.50.1"
BACKUP_DIR = "/home/inove/backups"
TELEGRAM_TOKEN = "8306509380:AAFLi6-UoFo4GZxmc_Q3rU8xZIeLdd6mmWY"
TELEGRAM_CHAT_ID = "-1003559071567"
LOG_FILE = "/home/inove/oltdatacom/backup_datacom.log"

# =========================================================
# CRIAR DIRETÓRIOS SE NÃO EXISTIREM
# =========================================================
def setup_directories():
    """Cria os diretórios necessários se não existirem"""
    dirs_to_create = [
        BACKUP_DIR,
        os.path.dirname(LOG_FILE)
    ]
    
    for directory in dirs_to_create:
        if not os.path.exists(directory):
            try:
                os.makedirs(directory, exist_ok=True)
                print(f"✓ Diretório criado: {directory}")
            except Exception as e:
                print(f"✗ Erro ao criar diretório {directory}: {e}")
                raise

# Criar diretórios ANTES de configurar o logging
setup_directories()

# =========================================================
# LOGGING
# =========================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
log = logging.getLogger("BACKUP-DATACOM")

# =========================================================
# FUNÇÕES AUXILIARES
# =========================================================
def telegram_send_message(text):
    try:
        log.info(f"Telegram MSG: {text}")
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text
        }, timeout=10)
    except Exception as e:
        log.error(f"Erro ao enviar mensagem Telegram: {e}")

def telegram_send_file(file_path):
    try:
        log.info(f"Telegram FILE: enviando {file_path}")
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendDocument"
        with open(file_path, "rb") as f:
            requests.post(
                url,
                data={"chat_id": TELEGRAM_CHAT_ID},
                files={"document": f},
                timeout=30
            )
    except Exception as e:
        log.error(f"Erro ao enviar arquivo Telegram: {e}")

def send_command(tn, command, wait=2):
    log.info(f"OLT CMD >> {command}")
    tn.write(command.encode("ascii") + b"\n")
    time.sleep(wait)
    response = tn.read_very_eager().decode("ascii", errors="ignore")
    if response.strip():
        log.info(f"OLT RESP << {response.strip()}")
    return response

# =========================================================
# BACKUP DATACOM
# =========================================================
def backup_datacom(olt_name, olt):
    ip = olt["ip"]
    user = olt["user"]
    password = olt["password"]
    
    telegram_send_message(f"🔄 Iniciando backup da OLT {olt_name}")
    log.info(f"===== INÍCIO BACKUP OLT {olt_name} ({ip}) =====")
    
    try:
        log.info("Conectando via Telnet...")
        tn = telnetlib.Telnet(ip, 23, timeout=20)
        
        tn.read_until(b"login:", timeout=15)
        tn.write(user.encode() + b"\n")
        
        tn.read_until(b"Password:", timeout=15)
        tn.write(password.encode() + b"\n")
        
        tn.read_until(b"Welcome to the DmOS CLI", timeout=20)
        log.info("Login realizado com sucesso")
        
        send_command(tn, "config")
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"backup_{olt_name}_{timestamp}.txt"
        log.info(f"Arquivo de backup: {filename}")
        
        # SALVAR BACKUP
        send_command(tn, f"save {filename}")
        log.info("Aguardando 90s para gravação interna da OLT...")
        time.sleep(90)
        
        # ENVIAR PARA TFTP
        send_command(
            tn,
            f"copy file {filename} tftp://{TFTP_HOST}",
            wait=90
        )
        log.info("Comando de envio TFTP executado")
        
        tn.write(b"exit\n")
        tn.close()
        log.info("Sessão Telnet encerrada")
        
        local_file = os.path.join(BACKUP_DIR, filename)
        log.info("Aguardando arquivo chegar via TFTP...")
        
        last_size = -1
        stable_count = 0
        
        for i in range(90):
            if os.path.exists(local_file):
                size = os.path.getsize(local_file)
                log.info(f"TFTP recebendo ({i*2}s): {size} bytes")
                
                if size == last_size and size > 0:
                    stable_count += 1
                else:
                    stable_count = 0
                
                last_size = size
                
                if stable_count >= 5:
                    log.info("Arquivo TFTP finalizado")
                    telegram_send_file(local_file)
                    telegram_send_message(f"✅ Backup OLT {olt_name} concluído com sucesso")
                    log.info(f"===== FIM BACKUP OLT {olt_name} =====")
                    return
            
            time.sleep(2)
        
        telegram_send_message(f"❌ Backup OLT {olt_name} não finalizou a tempo")
        log.error("Timeout aguardando TFTP")
        
    except Exception as e:
        log.exception(f"Erro no backup da OLT {olt_name}")
        telegram_send_message(f"🚨 Erro no backup da OLT {olt_name}: {e}")

# =========================================================
# EXECUÇÃO PRINCIPAL
# =========================================================
def main():
    log.info("########## INICIANDO SCRIPT DE BACKUP DATACOM ##########")
    telegram_send_message("🚀 Iniciando processo de backup das OLTs Datacom")
    
    for olt_name, olt in OLTS.items():
        backup_datacom(olt_name, olt)
    
    telegram_send_message("🏁 Processo de backup Datacom finalizado")
    log.info("########## SCRIPT FINALIZADO ##########")

if __name__ == "__main__":
    main()

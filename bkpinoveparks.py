import telnetlib
import ftplib
import requests
import os
from datetime import datetime
from dotenv import load_dotenv

# Carregar variáveis do .env
load_dotenv()

# Lista de OLTs (Parks)
olts = [
    {
        "host": os.getenv("OLT_PARKS_IP"),
        "name": "OLT_PARKS_",
        "port": int(os.getenv("OLT_PARKS_PORT", "23")),
        "protocol": "telnet"
    },
]

# Credenciais
olt_user = os.getenv("OLT_PARKS_USER")
olt_password = os.getenv("OLT_PARKS_PASS")

# FTP
ftp_user = os.getenv("FTP_USER")
ftp_password = os.getenv("FTP_PASSWORD")
ftp_host = os.getenv("FTP_HOST")

# Diretório de backups
backup_dir = os.getenv("LOCAL_BACKUP_PATH", "/home/bkpoltparks/")

# Criar diretório se não existir
if not os.path.exists(backup_dir):
    os.makedirs(backup_dir)

# Telegram
telegram_bot_token = os.getenv("TELEGRAM_TOKEN")
telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID")


def telnet_backup(olt):
    try:
        olt_host = olt["host"]
        olt_name = olt["name"]
        olt_port = olt["port"]
        olt_protocol = olt["protocol"]
        
        print(f"Iniciando backup da OLT {olt_name} ({olt_host}) via {olt_protocol} na porta {olt_port}...")
        # Captura a data e hora atual
        timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        ftp_file = f"{olt_name}_backup_{timestamp}.bin"  # Nome do arquivo no FTP
        local_file = f"{backup_dir}{ftp_file}"  # Local para armazenar o backup
        
        # Conexão Telnet com a OLT
        tn = telnetlib.Telnet(olt_host, olt_port)
        
        # Aguarda pela mensagem "Press <RETURN> to get started"
        tn.read_until(b"Press <RETURN> to get started")
        
        # Envia <ENTER> para prosseguir
        tn.write(b"\n")
        
        # Aguardar até aparecer o prompt de login
        tn.read_until(b"Username: ")
        tn.write(olt_user.encode('ascii') + b"\n")
        
        # Aguardar até aparecer o prompt de senha
        tn.read_until(b"Password: ")
        tn.write(olt_password.encode('ascii') + b"\n")

        # Executa o comando para realizar o backup na OLT
        backup_command = f"copy startup-config ftp://{ftp_host}/{ftp_file} {ftp_user} {ftp_password}\n"
        tn.write(backup_command.encode('ascii'))
        tn.write(b"exit\n")

        # Aguarda e fecha a conexão Telnet
        tn.read_all()
        tn.close()
        print(f"Backup da OLT {olt_name} realizado com sucesso.")
        
        # Processar o arquivo de backup
        download_backup(ftp_file, local_file)
        send_to_telegram(local_file, olt_name, timestamp)
        cleanup(local_file)
        
    except Exception as e:
        print(f"Erro durante o backup da OLT {olt_name}: {e}")

def download_backup(ftp_file, local_file):
    try:
        # Conectar ao servidor FTP para baixar o arquivo
        ftp = ftplib.FTP(ftp_host)
        ftp.login(ftp_user, ftp_password)

        with open(local_file, 'wb') as f:
            ftp.retrbinary(f"RETR {ftp_file}", f.write)
        
        ftp.quit()
        print(f"Arquivo {ftp_file} baixado com sucesso do FTP.")
    except Exception as e:
        print(f"Erro durante o download do backup {ftp_file}: {e}")

def send_to_telegram(local_file, olt_name, timestamp):
    try:
        url = f"https://api.telegram.org/bot{telegram_bot_token}/sendDocument"
        files = {'document': open(local_file, 'rb')}
        data = {'chat_id': telegram_chat_id, 'caption': f'Backup da {olt_name} realizado com sucesso em {timestamp}.'}
        response = requests.post(url, files=files, data=data)
        
        if response.status_code == 200:
            print(f"Backup da {olt_name} enviado com sucesso para o Telegram.")
        else:
            print(f"Erro ao enviar o backup da {olt_name} para o Telegram: {response.status_code}, {response.text}")
    except Exception as e:
        print(f"Erro durante o envio para o Telegram: {e}")

def cleanup(local_file):
    try:
        os.remove(local_file)
        print(f"Arquivo temporário {local_file} excluído.")
    except OSError as e:
        print(f"Erro ao excluir o arquivo temporário {local_file}: {e}")

if __name__ == "__main__":
    for olt in olts:
        telnet_backup(olt)

# OLT Backup — Multi-Vendor (Docker)

Sistema modular de backup automatizado de OLTs com suporte a múltiplos fabricantes. Roda em Docker com agendamento automático via scheduler Python e envia notificações e arquivos de backup diretamente ao Telegram.

> **Timezone:** fixo em `America/Bahia` em todo o sistema (scheduler, Docker, sistema operacional).

---

## Instalação Rápida (servidor limpo)

Execute o script de setup em uma linha — ele instala o Docker, configura o ambiente e clona o repositório automaticamente:

```bash
curl -fsSL https://raw.githubusercontent.com/Br10Consultoria/bkpolts/main/setup.sh | sudo bash
```

Ou, se já tiver o repositório clonado:

```bash
sudo bash setup.sh
```

O script realiza automaticamente:

| Etapa | Descrição |
|---|---|
| 1 | Detecta a distribuição Linux (Ubuntu, Debian, CentOS, RHEL, Rocky) |
| 2 | Instala dependências base (`curl`, `git`, `tzdata`, `nano`) |
| 3 | Instala Docker Engine + Docker Compose plugin (repositório oficial) |
| 4 | Habilita e inicia o serviço Docker |
| 5 | Adiciona o usuário atual ao grupo `docker` (sem necessidade de `sudo`) |
| 6 | Configura timezone do sistema para `America/Bahia` |
| 7 | Clona o repositório em `/opt/bkpolts` |
| 8 | Cria o `.env` a partir do `.env.example` |
| 9 | Exibe instruções finais de uso |

Após o setup, edite o `.env` e suba o container:

```bash
nano /opt/bkpolts/.env
cd /opt/bkpolts && docker compose up -d --build
```

---

## Arquitetura

```
bkpolts/
├── setup.sh                # Instalação automática do Docker + ambiente
├── Dockerfile              # Imagem Docker (única para todos os vendors)
├── docker-compose.yml      # Orquestração do container
├── entrypoint.sh           # Inicia o scheduler.py ao subir o container
├── run.py                  # CLI interativo para backup manual
├── scheduler.py            # Daemon de agendamento (13h e 22h)
├── requirements.txt        # Dependências Python
├── .env                    # Credenciais e configuração (NÃO versionado)
├── .env.example            # Modelo de configuração
│
├── common/                 # Módulo compartilhado por todos os vendors
│   ├── __init__.py
│   ├── telegram.py         # Envio de mensagens e arquivos ao Telegram
│   ├── helpers.py          # Logging, Telnet, FTP download, cleanup
│   └── parser.py           # Parser de OLTs a partir do .env
│
└── vendors/                # Um diretório por fabricante
    ├── datacom/
    │   └── backup.py       # Datacom — Telnet + SFTP/SCP
    ├── zte/
    │   └── backup.py       # ZTE padrão + ZTE Titan — Telnet + FTP
    ├── parks/
    │   └── backup.py       # Parks — Telnet + FTP
    ├── fiberhome/
    │   └── backup.py       # Fiberhome — Telnet + FTP
    └── huawei/
        └── backup.py       # Huawei — Telnet + FTP
```

---

## Como funciona

O `scheduler.py` é um daemon Python que:

1. Lê as variáveis `VENDOR`, `CRON_HOUR_1` e `CRON_HOUR_2` do `.env`
2. Aguarda os horários configurados (padrão: **13:00** e **22:00**)
3. Executa automaticamente os scripts de backup dos vendors configurados
4. **Recarrega o `.env` a cada ciclo** — mudanças de configuração não exigem reinicialização do container

O `run.py` é o CLI interativo para execução manual, com menu de seleção de vendor.

| Variável | Descrição | Padrão |
|---|---|---|
| `VENDOR` | Vendors a executar (vírgula) | detectado automaticamente |
| `CRON_HOUR_1` | Primeiro horário do dia | `13` |
| `CRON_HOUR_2` | Segundo horário do dia | `22` |

> **Timezone:** sempre `America/Bahia` — fixo no scheduler, Docker e sistema operacional.

---

## Protocolos por Vendor

| Vendor | Protocolo de acesso | Protocolo de transferência |
|---|---|---|
| **Datacom** | Telnet | SFTP/SCP (`DATACOM_COPY_SCHEME`) |
| **ZTE** | Telnet | FTP |
| **ZTE Titan** | Telnet | FTP |
| **Parks** | Telnet | FTP |
| **Fiberhome** | Telnet | FTP |
| **Huawei** | Telnet | FTP |

---

## Servidor de backup Datacom (SFTP/SCP)

O backup Datacom não depende mais de um servidor TFTP (que nunca chegou a existir neste projeto — era a causa dos backups "enviados mas nunca recebidos"). Em vez disso, a própria OLT envia o arquivo via SFTP/SCP para um usuário SSH dedicado e restrito (chroot) no host Debian/Ubuntu que roda o Docker. Como o `sshd` já vem instalado por padrão em qualquer distro dessas, não é preciso instalar nada além do OpenSSH.

> **Antes de tudo:** conecte via telnet numa OLT, entre em `config` e rode `copy ?` para confirmar se o firmware aceita `sftp://` ou `scp://` como destino. Ajuste `DATACOM_COPY_SCHEME` no `.env` conforme o resultado — o código não precisa mudar.

### 1. Criar o usuário dedicado no host (fora do container)

```bash
sudo mkdir -p /srv/olt-backups/upload
sudo adduser --disabled-password --gecos "" --home /srv/olt-backups oltbackup
sudo passwd oltbackup                       # defina a senha usada em DATACOM_BACKUP_PASSWORD
sudo chown root:root /srv/olt-backups       # exigido pelo sshd: raiz do chroot não pode ser gravável pelo usuário
sudo chmod 755 /srv/olt-backups
sudo chown oltbackup:oltbackup /srv/olt-backups/upload
sudo chmod 700 /srv/olt-backups/upload
```

### 2. Restringir o usuário a SFTP com chroot (`/etc/ssh/sshd_config`)

```
Match User oltbackup
    ChrootDirectory /srv/olt-backups
    ForceCommand internal-sftp
    PasswordAuthentication yes
    AllowTcpForwarding no
    X11Forwarding no
```

```bash
sudo systemctl restart sshd
```

Se o firmware da OLT só aceitar `scp://` (protocolo SCP puro, não SFTP), o `ForceCommand internal-sftp` acima não serve — troque por `ForceCommand /usr/lib/openssh/sftp-server` **ou**, se realmente for SCP raiz, remova o `ForceCommand` e restrinja via `scp` no lugar de um shell completo (ex.: `usermod -s /usr/bin/scp oltbackup` não é suportado diretamente; nesse caso use `rssh` ou `scponly`). Isso só é necessário se o `copy ?` confirmar que a OLT fala SCP e não SFTP.

### 3. Apontar o `.env` para esse usuário e diretório

```env
DATACOM_BACKUP_HOST=10.0.0.1            # IP do host onde o sshd está rodando
DATACOM_BACKUP_USER=oltbackup
DATACOM_BACKUP_PASSWORD=SENHA_FORTE_AQUI
DATACOM_BACKUP_PATH=                    # vazio = grava direto em /srv/olt-backups/upload
DATACOM_COPY_SCHEME=sftp                # ou "scp", conforme confirmado no `copy ?`
DATACOM_BACKUP_SFTP_DIR=/srv/olt-backups/upload
```

`DATACOM_BACKUP_SFTP_DIR` faz o `docker-compose.yml` montar exatamente essa pasta do host como `/app/backups` dentro do container — é assim que o script Python enxerga o arquivo que a OLT acabou de enviar via SFTP, sem precisar de nenhuma outra ponte entre host e container.

### 4. Recriar o container para aplicar o bind mount

```bash
docker compose up -d --build
```

---

## Instalação Manual (sem o setup.sh)

### 1. Instalar Docker

```bash
curl -fsSL https://get.docker.com | bash
sudo usermod -aG docker $USER
```

### 2. Clonar o repositório

```bash
git clone https://github.com/Br10Consultoria/bkpolts.git
cd bkpolts
```

### 3. Configurar credenciais

```bash
cp .env.example .env
nano .env
```

Preencha as OLTs no formato `NOME:IP:USUARIO:SENHA` separadas por vírgula:

```env
# Vendors a executar
VENDOR=datacom,zte

# Horários de execução
CRON_HOUR_1=13
CRON_HOUR_2=22

# Telegram
TELEGRAM_TOKEN=seu_token
TELEGRAM_CHAT_ID=seu_chat_id

# OLTs
DATACOM_OLTS=DC1:172.24.25.2:backupolt:MinhaSenh@,DC2:172.24.25.6:backupolt:MinhaSenh@
ZTE_OLTS=ZTE_ARAMARI:10.100.11.2:sgpoltzte:MinhaSenh@
ZTE_TITAN_OLTS=ZTE_TITAN_CANAVIEIRAS:10.11.10.10:sgpoltzte:MinhaSenh@
```

### 4. Subir o container

```bash
docker compose up -d --build
```

### 5. Verificar inicialização

```bash
docker logs olt-backup
```

Saída esperada:

```
╔══════════════════════════════════════════════════════╗
║         OLT Backup Docker — Multi-Vendor            ║
║         Br10 Consultoria                            ║
╚══════════════════════════════════════════════════════╝

  Vendors   : datacom,zte
  Horários  : 13:00 e 22:00
  Timezone  : America/Bahia (fixo)

2026-01-01 10:00:00 | INFO | Timezone  : America/Bahia
2026-01-01 10:00:00 | INFO | Horários  : 13:00 e 22:00
2026-01-01 10:00:00 | INFO | Vendors   : datacom, zte
```

---

## Uso — Backup Manual (CLI Interativo)

### Menu interativo

```bash
# Dentro do container
docker exec -it olt-backup python3 /app/run.py

# Fora do container (com .env no diretório atual)
python3 run.py
```

Saída do menu:

```
╔══════════════════════════════════════════════════════╗
║         OLT Backup — Multi-Vendor CLI                ║
║         Br10 Consultoria                             ║
╚══════════════════════════════════════════════════════╝

  Vendors disponíveis (com OLTs configuradas no .env):

  [1] Datacom   (Telnet + SFTP/SCP)                    ✔  2 OLT(s)
  [2] ZTE       (Telnet + FTP)  — padrão + Titan      ✔  2 OLT(s)
  [3] Parks     (Telnet + FTP)                        ✘  sem OLTs configuradas
  [4] Fiberhome (Telnet + FTP)                        ✘  sem OLTs configuradas
  [5] Huawei    (Telnet + FTP)                        ✘  sem OLTs configuradas

  [A] Executar TODOS os vendors configurados
  [0] Sair

  Selecione uma opção:
```

### Execução direta por vendor

```bash
# Via argumento (sem menu)
python3 run.py --vendor datacom
python3 run.py --vendor zte
python3 run.py --vendor parks
python3 run.py --vendor fiberhome
python3 run.py --vendor huawei

# Todos os vendors configurados
python3 run.py --all

# Listar vendors e quantidade de OLTs
python3 run.py --list
```

### Execução imediata via scheduler

```bash
# Executa todos os vendors agora (sem aguardar horário agendado)
python3 scheduler.py --now

# Ver configuração atual do scheduler
python3 scheduler.py --status
```

---

## Uso — Dentro do Container Docker

```bash
# Menu interativo
docker exec -it olt-backup python3 /app/run.py

# Vendor específico
docker exec olt-backup python3 /app/run.py --vendor zte
docker exec olt-backup python3 /app/run.py --vendor datacom

# Todos os vendors imediatamente
docker exec olt-backup python3 /app/scheduler.py --now

# Status do scheduler
docker exec olt-backup python3 /app/scheduler.py --status

# Ver logs
docker compose logs -f olt-backup
docker exec olt-backup cat /app/logs/scheduler.log
docker exec olt-backup cat /app/logs/backup_datacom.log
docker exec olt-backup cat /app/logs/backup_zte.log

# Parar
docker compose down

# Reconstruir após alterar scripts
docker compose up -d --build
```

---

## Formato das OLTs no .env

Todas as OLTs seguem o mesmo formato:

```
VENDOR_OLTS=NOME1:IP:USUARIO:SENHA,NOME2:IP:USUARIO:SENHA
```

Se a senha contiver `:`, não há problema — o parser reconhece que tudo após o terceiro `:` é a senha.

---

## Notificações Telegram

Cada vendor envia ao Telegram:

1. Mensagem de início com total de OLTs.
2. Após cada OLT: arquivo de backup + mensagem de sucesso ou falha com progresso `[1/5]`.
3. Resumo final com lista de sucessos e falhas.

---

## Adicionar um novo vendor

1. Crie o diretório `vendors/novovendor/`.
2. Crie o arquivo `vendors/novovendor/backup.py` seguindo o padrão dos demais.
3. Adicione `NOVOVENDOR_OLTS=...` no `.env`.
4. Adicione `novovendor` na variável `VENDOR` do `.env`.
5. Adicione a entrada em `VENDOR_MAP` nos arquivos `run.py` e `scheduler.py`.
6. Reconstrua o container: `docker compose up -d --build`.

---

## Observações sobre Fiberhome e Huawei

Os scripts de Fiberhome e Huawei incluem comandos genéricos que podem precisar de ajuste conforme o modelo e firmware específico da sua OLT. Os pontos de ajuste estão marcados com comentários no código:

```python
# ============================================================
# AJUSTE ESTE COMANDO conforme o modelo/firmware da sua OLT
# ============================================================
```

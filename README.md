# OLT Backup — Multi-Vendor (Docker)

Sistema modular de backup automatizado de OLTs com suporte a múltiplos fabricantes. Roda em Docker com agendamento automático via scheduler Python e envia notificações e arquivos de backup diretamente ao Telegram.

---

## Arquitetura

```
bkpolts/
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
    │   └── backup.py       # Datacom — Telnet + TFTP
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

1. Lê as variáveis `VENDOR`, `CRON_HOUR_1`, `CRON_HOUR_2` e `TZ` do `.env`
2. Aguarda os horários configurados (padrão: **13:00** e **22:00**)
3. Executa automaticamente os scripts de backup dos vendors configurados
4. **Recarrega o `.env` a cada ciclo** — mudanças de configuração não exigem reinicialização do container

O `run.py` é o CLI interativo para execução manual, com menu de seleção de vendor.

| Variável | Descrição | Padrão |
|---|---|---|
| `VENDOR` | Vendors a executar (vírgula) | detectado automaticamente |
| `CRON_HOUR_1` | Primeiro horário do dia | `13` |
| `CRON_HOUR_2` | Segundo horário do dia | `22` |
| `TZ` | Timezone | `America/Bahia` |

---

## Protocolos por Vendor

| Vendor | Protocolo de acesso | Protocolo de transferência |
|---|---|---|
| **Datacom** | Telnet | TFTP |
| **ZTE** | Telnet | FTP |
| **ZTE Titan** | Telnet | FTP |
| **Parks** | Telnet | FTP |
| **Fiberhome** | Telnet | FTP |
| **Huawei** | Telnet | FTP |

---

## Instalação

### 1. Clonar o repositório

```bash
git clone https://github.com/Br10Consultoria/bkpolts.git
cd bkpolts
```

### 2. Configurar credenciais

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
TZ=America/Bahia

# Telegram
TELEGRAM_TOKEN=seu_token
TELEGRAM_CHAT_ID=seu_chat_id

# OLTs
DATACOM_OLTS=DC1:172.24.25.2:backupolt:MinhaSenh@,DC2:172.24.25.6:backupolt:MinhaSenh@
ZTE_OLTS=ZTE_ARAMARI:10.100.11.2:sgpoltzte:MinhaSenh@
ZTE_TITAN_OLTS=ZTE_TITAN_CANAVIEIRAS:10.11.10.10:sgpoltzte:MinhaSenh@
```

### 3. Subir o container

```bash
docker compose up -d --build
```

### 4. Verificar inicialização

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
  Timezone  : America/Bahia

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

  [1] Datacom   (Telnet + TFTP)                       ✔  2 OLT(s)
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

# OLT Backup — Multi-Vendor (Docker)

Sistema modular de backup automatizado de OLTs, com suporte a múltiplos fabricantes. Roda em Docker com agendamento via cron e envia notificações e arquivos de backup diretamente ao Telegram.

---

## Arquitetura

```
bkpolts/
├── Dockerfile              # Imagem Docker (única para todos os vendors)
├── docker-compose.yml      # Orquestração do container
├── entrypoint.sh           # Gera crontab dinamicamente conforme VENDOR
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

O `entrypoint.sh` lê a variável `VENDOR` do `.env` e gera o crontab automaticamente apenas para os vendors selecionados. Você controla **tudo** pelo `.env`:

| Variável | Descrição | Exemplo |
|---|---|---|
| `VENDOR` | Vendors a executar (vírgula) | `datacom,zte,parks` |
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
VENDOR=datacom,zte

DATACOM_OLTS=DC1:172.24.25.2:backupolt:MinhaSenh@,DC2:172.24.25.6:backupolt:MinhaSenh@
ZTE_OLTS=ZTE_ARAMARI:10.100.11.2:sgpoltzte:MinhaSenh@
ZTE_TITAN_OLTS=ZTE_TITAN_CANAVIEIRAS:10.11.10.10:sgpoltzte:MinhaSenh@
```

### 3. Subir o container

```bash
docker compose up -d --build
```

### 4. Verificar se o cron foi configurado

```bash
docker logs olt-backup
```

Saída esperada:

```
[OK] Vendor 'datacom' agendado às 13:00 e 22:00
[OK] Vendor 'zte' agendado às 13:00 e 22:00
=============================================
  OLT Backup Docker — Multi-Vendor
  Vendors: datacom,zte
  Horários: 13:00 e 22:00 (America/Bahia)
=============================================
```

---

## Uso

### Executar backup manualmente (teste)

```bash
# Testar um vendor específico
docker exec olt-backup python3 /app/vendors/datacom/backup.py
docker exec olt-backup python3 /app/vendors/zte/backup.py
docker exec olt-backup python3 /app/vendors/parks/backup.py
```

### Ver logs

```bash
# Logs do container
docker compose logs -f olt-backup

# Log de um vendor específico
docker exec olt-backup cat /app/logs/backup_datacom.log
docker exec olt-backup cat /app/logs/backup_zte.log
```

### Parar

```bash
docker compose down
```

### Reconstruir após alterar scripts

```bash
docker compose up -d --build
```

---

## Adicionar um novo vendor

1. Crie o diretório `vendors/novovendor/`.
2. Crie o arquivo `vendors/novovendor/backup.py` seguindo o padrão dos demais.
3. Adicione `NOVOVENDOR_OLTS=...` no `.env`.
4. Adicione `novovendor` na variável `VENDOR` do `.env`.
5. Reconstrua o container: `docker compose up -d --build`.

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

## Observações sobre Fiberhome e Huawei

Os scripts de Fiberhome e Huawei incluem comandos genéricos que podem precisar de ajuste conforme o modelo e firmware específico da sua OLT. Os pontos de ajuste estão marcados com comentários no código:

```python
# ============================================================
# AJUSTE ESTE COMANDO conforme o modelo/firmware da sua OLT
# ============================================================
```

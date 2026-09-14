# OLT Backup — Multi-Vendor (Docker)

Sistema modular de backup automatizado de OLTs com seleção de fabricante e modelo. Cada modelo usa seu próprio driver e os comandos homologados para ele. O instalador provisiona scheduler, painel web e receptores TFTP, FTP e SCP/SFTP, com armazenamento compartilhado e envio ao Telegram.

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
| 9 | Detecta o IP principal e gera senhas fortes para painel, FTP e SCP/SFTP |
| 10 | Configura UFW/firewalld quando presente |
| 11 | Constrói, inicia e verifica todos os containers |
| 12 | Exibe URL e credenciais iniciais do painel |

Após o setup, abra a URL exibida pelo instalador e cadastre as OLTs escolhendo fabricante e modelo. Para conferir os serviços:

```bash
cd /opt/bkpolts && docker compose ps
```

---

## Arquitetura

```
bkpolts/
├── setup.sh                # Instalação automática do Docker + ambiente
├── Dockerfile              # Imagem Docker (única para todos os vendors + webui)
├── docker-compose.yml      # Scheduler, webui e receptores TFTP/FTP/SCP-SFTP
├── entrypoint.sh           # Inicia o scheduler.py ao subir o container
├── run.py                  # CLI interativo para backup manual
├── scheduler.py            # Daemon de agendamento (13h e 22h)
├── requirements.txt        # Dependências Python
├── .env                    # Credenciais e configuração (NÃO versionado)
├── .env.example            # Modelo de configuração
│
├── tftp/
│   └── Dockerfile          # Servidor TFTP
├── ftp/
│   └── Dockerfile          # Servidor FTP (vsftpd)
├── sftp/
│   └── Dockerfile          # Servidor SCP/SFTP (OpenSSH)
│
├── common/                 # Módulo compartilhado por todos os vendors
│   ├── __init__.py
│   ├── telegram.py         # Envio de mensagens e arquivos ao Telegram
│   ├── helpers.py          # Logging, Telnet, FTP download, cleanup
│   ├── parser.py           # Parser de OLTs a partir do .env
│   ├── env_store.py        # Leitura/escrita do .env usada pela interface web
│   └── vendors.py          # Catálogo central de marcas, modelos e protocolos
│
├── webui/                  # Interface web (cadastro de OLTs + backup manual)
│   ├── app.py               # App Flask (login, rotas, disparo de backup)
│   └── templates/
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

## Modelos e protocolos homologados

| Vendor/modelo | Protocolo de acesso | Protocolo de transferência |
|---|---|---|
| **Datacom DM4615/DM4618/DmOS** | Telnet | TFTP |
| **ZTE C300/C320/C350** | Telnet | FTP |
| **ZTE Titan/C600** | Telnet | FTP |
| **Parks Fiberlink** | Telnet | FTP |
| **Fiberhome AN5516/AN6000** | Telnet | FTP |
| **Huawei MA5600/MA5800** | Telnet | FTP |
| **Intelbras G16** | Telnet | FTP ou TFTP |

Os três receptores ficam disponíveis no servidor. SCP/SFTP usa a porta `2222` por padrão para não conflitar com o SSH administrativo. Um protocolo só aparece como suportado por um modelo quando seu comando foi homologado no driver, evitando enviar sintaxe incompatível a uma OLT.

O catálogo de runtime fica centralizado em `common/vendors.py`. Para um modelo novo, adicione a definição ao catálogo e implemente ou reutilize o driver do fabricante; CLI, scheduler, testes e painel passam a reconhecê-lo juntos.

---

## Servidor de backup Datacom (TFTP)

O comando de backup confirmado contra uma sessão real de produção é:

```
show running-config | save overwrite <arquivo>     # direto no prompt exec, sem entrar em "config"
copy file <arquivo> tftp://<TFTP_IP>
```

O `docker-compose.yml` já sobe um terceiro serviço, `tftp` (Dockerfile em `tftp/`, baseado em `tftpd-hpa`), então não precisa instalar nem configurar nada à parte no host — só apontar `TFTP_IP` para o IP deste mesmo servidor.

> TFTP negocia a transferência de dados numa porta UDP efêmera (não fixa na 69), o que não atravessa o NAT do modo bridge padrão do Docker — por isso os três serviços (`olt-backup`, `webui`, `tftp`) rodam com `network_mode: host`. Isso já vem configurado; não precisa mexer.

### 1. Configurar o `.env` (ou a interface web, em Configurações)

```env
TFTP_IP=10.0.0.1              # IP deste servidor
DATACOM_BACKUP_DIR=           # vazio = usa um volume Docker nomeado comum
```

`DATACOM_BACKUP_DIR`, se preenchido com um caminho absoluto (ex.: `/srv/olt-backups`), faz o `docker-compose.yml` montar essa pasta do host tanto no container `tftp` (que grava o arquivo recebido) quanto em `olt-backup`/`webui` (que leem o arquivo e mandam ao Telegram) — os três enxergam exatamente o mesmo diretório. Deixar em branco também funciona (usa um volume Docker nomeado interno), só fica menos prático se um dia você quiser inspecionar os arquivos direto pelo filesystem do host.

### 2. Subir os containers

```bash
docker compose up -d --build
```

---

## Interface Web

O instalador sobe cinco serviços: `olt-backup` (scheduler), `webui` (painel), `tftp`, `ftp` e `sftp` (SCP/SFTP). O painel escuta em `http://<ip-do-servidor>:8080` e o instalador exibe a senha inicial gerada automaticamente.

Login: usuário/senha definidos em `WEBUI_USER` / `WEBUI_PASSWORD` no `.env`. **Não exponha essa porta na internet** mesmo com login habilitado — mantenha atrás de VPN/firewall, como já se faz hoje com o acesso Telnet às próprias OLTs.

O que dá pra fazer pelo painel:
- Cadastrar, listar e remover OLTs por vendor (grava direto no `.env`, mesmo formato `NOME:IP:USUARIO:SENHA` usado pelo resto do projeto).
- Editar nome, IP, usuário e senha de uma OLT sem recriar o cadastro.
- Ativar ou desativar individualmente uma OLT; equipamentos desativados são preservados, mas ignorados pelo scheduler e pelos backups manuais.
- Disparar o backup de uma OLT específica ou de todas as OLTs de um vendor, sem esperar o horário agendado.
- Acompanhar o log da última execução de cada vendor, e limpar esse log quando quiser.
- Parar ou forçar a parada de um backup travado. O sinal de cancelamento e o estado são compartilhados entre Web UI, scheduler e CLI; o status obsoleto é removido automaticamente se um container cair. A sessão na OLT pode levar alguns segundos para encerrar.
- Editar Telegram e o `TFTP_IP`/diretório de backup do Datacom.

Se quiser rodar sem Docker (ex.: pra debugar): `python3 webui/app.py` (lê o `.env` da raiz do projeto).

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

  [1] Datacom   (Telnet + TFTP)                        ✔  2 OLT(s)
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

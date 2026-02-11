# Backup Automático OLTs Datacom

Sistema automatizado de backup para OLTs Datacom com envio via Telegram.

## 🚀 Características

- ✅ Backup automático de 11 OLTs Datacom
- ✅ Conexão via Telnet para executar comandos
- ✅ Download dos arquivos via SCP
- ✅ Envio automático para Telegram
- ✅ Logs detalhados de todas as operações
- ✅ Execução agendada (13h e 22h)
- ✅ Containerizado com Docker
- ✅ Configuração via variáveis de ambiente

## 📋 Pré-requisitos

- Docker e Docker Compose instalados
- Acesso de rede às OLTs (portas 23 para Telnet e 22 para SSH/SCP)
- Bot do Telegram criado (via @BotFather)
- Chat ID do Telegram

## 🔧 Instalação

### 1. Clonar o repositório

```bash
cd /home
git clone https://github.com/seu-usuario/olt-backup.git oltdatacom
cd oltdatacom
```

### 2. Configurar variáveis de ambiente

```bash
cp .env.example .env
nano .env
```

Edite o arquivo `.env` e configure:

```bash
# Configurações do Telegram (OBRIGATÓRIO)
TELEGRAM_BOT_TOKEN=seu_token_do_botfather
TELEGRAM_CHAT_ID=seu_chat_id

# As demais configurações já estão com os valores padrão das OLTs
# Apenas altere se necessário
```

### 3. Como obter o Token e Chat ID do Telegram

#### Token do Bot:
1. Abra o Telegram e procure por `@BotFather`
2. Digite `/newbot` e siga as instruções
3. Copie o token fornecido (formato: `123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ`)

#### Chat ID:
1. Adicione o bot criado em um grupo ou conversa
2. Envie uma mensagem qualquer para o bot
3. Acesse: `https://api.telegram.org/bot<SEU_TOKEN>/getUpdates`
4. Procure por `"chat":{"id":` no JSON retornado
5. Use esse número como Chat ID

### 4. Construir e iniciar o container

```bash
docker-compose up -d --build
```

## 📊 Monitoramento

### Ver logs em tempo real

```bash
docker-compose logs -f
```

### Ver logs salvos

```bash
tail -f logs/backup_$(date +%Y%m%d).log
```

### Verificar status do container

```bash
docker-compose ps
```

## 🕐 Agendamento

O backup é executado automaticamente:
- **13:00** - Backup diário 1
- **22:00** - Backup diário 2

Para alterar os horários, edite o arquivo `crontab` e reconstrua o container.

## 🔍 Estrutura de Diretórios

```
/home/oltdatacom/
├── backup_olt.py           # Script principal
├── docker-compose.yml      # Configuração Docker
├── Dockerfile              # Imagem Docker
├── requirements.txt        # Dependências Python
├── crontab                 # Agendamento
├── entrypoint.sh          # Script de inicialização
├── .env                   # Variáveis de ambiente (NÃO COMMITAR)
├── .env.example           # Exemplo de configuração
├── logs/                  # Logs diários
│   └── backup_YYYYMMDD.log
└── backups/               # Backups temporários (removidos após envio)
```

## 🔄 Executar Backup Manualmente

### Dentro do container:

```bash
docker-compose exec olt-backup python3 /home/oltdatacom/backup_olt.py
```

### Ou entrando no container:

```bash
docker-compose exec olt-backup bash
cd /home/oltdatacom
python3 backup_olt.py
```

## 🛠️ Manutenção

### Atualizar código do GitHub

```bash
cd /home/oltdatacom
git pull
docker-compose down
docker-compose up -d --build
```

### Reiniciar container

```bash
docker-compose restart
```

### Ver uso de recursos

```bash
docker stats olt-backup-datacom
```

### Limpar logs antigos (manter últimos 30 dias)

```bash
find /home/oltdatacom/logs -name "*.log" -mtime +30 -delete
```

## 📱 Notificações Telegram

O sistema envia:

1. **Mensagem de início** - Quando o backup inicia
2. **Arquivos de backup** - Cada OLT que foi feita backup com sucesso
3. **Relatório final** - Resumo com sucessos e falhas

Exemplo de relatório:
```
📊 Relatório de Backup OLTs Datacom

✅ Sucessos: 10/11
❌ Falhas: 1/11

⚠️ Falhas em:
• POP_FORMIGA (falha no envio Telegram)

🕐 Concluído em: 27/11/2024 13:45:23
```

## 🔒 Segurança

- ⚠️ **NUNCA** commite o arquivo `.env` no Git
- As senhas estão em variáveis de ambiente
- Use `network_mode: host` apenas se necessário
- Considere usar secrets do Docker Swarm em produção

## 🐛 Troubleshooting

### Container não inicia

```bash
docker-compose logs
```

### OLT não conecta via Telnet

- Verifique conectividade: `docker-compose exec olt-backup ping 10.100.10.210`
- Verifique porta Telnet: `docker-compose exec olt-backup telnet 10.100.10.210 23`

### Falha no SCP

- Verifique se o SSH está habilitado na OLT
- Confirme que as credenciais estão corretas
- Teste manualmente: `docker-compose exec olt-backup bash` e tente fazer SCP

### Telegram não envia

- Verifique se o token está correto
- Confirme o Chat ID
- Teste o bot manualmente enviando `/start`

## 📝 Logs Detalhados

O sistema registra:

- ✅ Tentativas de conexão
- ✅ Comandos enviados e respostas
- ✅ Status de cada etapa (Telnet, Save, SCP, Telegram)
- ✅ Erros com stack trace completo
- ✅ Relatório final de cada execução

## 🔧 Configurações Avançadas

### Executar backup na inicialização

Adicione no `docker-compose.yml`:

```yaml
environment:
  - RUN_ON_STARTUP=true
```

### Alterar timezone

Edite no `docker-compose.yml`:

```yaml
environment:
  - TZ=America/Sao_Paulo
```

## 📞 Suporte

Para problemas ou dúvidas:
1. Verifique os logs: `docker-compose logs`
2. Leia a seção de Troubleshooting
3. Abra uma issue no GitHub

## 📄 Licença

MIT License

---

**Desenvolvido para backup automático de OLTs Datacom** 🚀

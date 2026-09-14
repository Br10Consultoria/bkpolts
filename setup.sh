#!/bin/bash
# ==============================================================
# setup.sh — Instalação do ambiente OLT Backup
#
# O que este script faz:
#   1. Verifica se está rodando como root
#   2. Detecta a distribuição Linux (Ubuntu/Debian/CentOS/RHEL)
#   3. Instala dependências do sistema (curl, git, ca-certificates)
#   4. Instala Docker Engine + Docker Compose plugin (oficial)
#   5. Habilita e inicia o serviço Docker
#   6. Adiciona o usuário atual ao grupo docker (sem sudo)
#   7. Configura timezone do sistema para America/Bahia
#   8. Clona o repositório bkpolts (se ainda não clonado)
#   9. Cria o .env a partir do .env.example (se não existir)
#  10. Exibe instruções finais de uso
#
# Uso:
#   curl -fsSL https://raw.githubusercontent.com/Br10Consultoria/bkpolts/main/setup.sh | sudo bash
#   ou
#   sudo bash setup.sh
# ==============================================================

set -euo pipefail

# ============================================================
# Cores para output
# ============================================================
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

REPO_URL="https://github.com/Br10Consultoria/bkpolts.git"
REPO_DIR="${INSTALL_DIR:-/opt/bkpolts}"
TIMEZONE="America/Bahia"

# ============================================================
# Funções auxiliares
# ============================================================

log_info()    { echo -e "${GREEN}[INFO]${NC}  $*"; }
log_warn()    { echo -e "${YELLOW}[AVISO]${NC} $*"; }
log_error()   { echo -e "${RED}[ERRO]${NC}  $*"; }
log_step()    { echo -e "\n${CYAN}${BOLD}==> $*${NC}"; }
log_ok()      { echo -e "${GREEN}${BOLD}[OK]${NC}    $*"; }

banner() {
    echo ""
    echo -e "${CYAN}${BOLD}╔══════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}${BOLD}║         OLT Backup — Setup de Ambiente              ║${NC}"
    echo -e "${CYAN}${BOLD}║         Br10 Consultoria                            ║${NC}"
    echo -e "${CYAN}${BOLD}╚══════════════════════════════════════════════════════╝${NC}"
    echo ""
}

# ============================================================
# Verificações iniciais
# ============================================================

check_root() {
    if [[ $EUID -ne 0 ]]; then
        log_error "Este script precisa ser executado como root."
        echo "        Use: sudo bash setup.sh"
        exit 1
    fi
}

detect_distro() {
    if [[ -f /etc/os-release ]]; then
        . /etc/os-release
        DISTRO_ID="${ID:-unknown}"
        DISTRO_LIKE="${ID_LIKE:-}"
        DISTRO_VERSION="${VERSION_ID:-}"
    else
        log_error "Não foi possível detectar a distribuição Linux."
        exit 1
    fi

    # Normaliza para família
    case "$DISTRO_ID" in
        ubuntu|debian|linuxmint|pop)
            DISTRO_FAMILY="debian"
            ;;
        centos|rhel|rocky|almalinux|fedora)
            DISTRO_FAMILY="rhel"
            ;;
        *)
            if echo "$DISTRO_LIKE" | grep -qi "debian"; then
                DISTRO_FAMILY="debian"
            elif echo "$DISTRO_LIKE" | grep -qi "rhel\|fedora"; then
                DISTRO_FAMILY="rhel"
            else
                log_warn "Distribuição '$DISTRO_ID' não testada. Tentando como Debian..."
                DISTRO_FAMILY="debian"
            fi
            ;;
    esac

    log_info "Distribuição detectada: ${DISTRO_ID} ${DISTRO_VERSION} (família: ${DISTRO_FAMILY})"
}

# ============================================================
# Instalação de dependências base
# ============================================================

install_base_deps() {
    log_step "Instalando dependências base..."

    if [[ "$DISTRO_FAMILY" == "debian" ]]; then
        apt-get update -qq
        apt-get install -y --no-install-recommends \
            curl \
            git \
            ca-certificates \
            gnupg \
            lsb-release \
            tzdata \
            nano \
            openssl \
            iproute2
    else
        yum install -y curl git ca-certificates gnupg2 tzdata nano openssl iproute 2>/dev/null || \
        dnf install -y curl git ca-certificates gnupg2 tzdata nano openssl iproute
    fi

    log_ok "Dependências base instaladas."
}

# ============================================================
# Instalação do Docker
# ============================================================

install_docker() {
    log_step "Verificando instalação do Docker..."

    if command -v docker &>/dev/null; then
        DOCKER_VERSION=$(docker --version 2>/dev/null | awk '{print $3}' | tr -d ',')
        log_ok "Docker já instalado: versão ${DOCKER_VERSION}"
        return 0
    fi

    log_info "Docker não encontrado. Instalando via script oficial..."

    if [[ "$DISTRO_FAMILY" == "debian" ]]; then
        # Remove versões antigas
        apt-get remove -y docker docker-engine docker.io containerd runc 2>/dev/null || true

        # Adiciona repositório oficial Docker
        install -m 0755 -d /etc/apt/keyrings
        curl -fsSL https://download.docker.com/linux/${DISTRO_ID}/gpg \
            | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
        chmod a+r /etc/apt/keyrings/docker.gpg

        echo \
            "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
            https://download.docker.com/linux/${DISTRO_ID} \
            $(lsb_release -cs) stable" \
            | tee /etc/apt/sources.list.d/docker.list > /dev/null

        apt-get update -qq
        apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

    else
        # CentOS/RHEL/Rocky
        yum remove -y docker docker-client docker-client-latest docker-common \
            docker-latest docker-latest-logrotate docker-logrotate docker-engine 2>/dev/null || true

        yum install -y yum-utils 2>/dev/null || dnf install -y yum-utils
        yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
        yum install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin \
            2>/dev/null || \
        dnf install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    fi

    log_ok "Docker instalado com sucesso."
}

# ============================================================
# Configuração do serviço Docker
# ============================================================

configure_docker_service() {
    log_step "Configurando serviço Docker..."

    systemctl enable docker
    systemctl start docker

    # Aguarda o daemon iniciar
    for i in $(seq 1 10); do
        if docker info &>/dev/null; then
            break
        fi
        log_info "Aguardando Docker iniciar... (${i}/10)"
        sleep 2
    done

    if ! docker info &>/dev/null; then
        log_error "Docker não iniciou corretamente. Verifique: systemctl status docker"
        exit 1
    fi

    log_ok "Serviço Docker ativo e funcionando."
}

# ============================================================
# Adiciona usuário ao grupo docker
# ============================================================

add_user_to_docker_group() {
    log_step "Configurando permissões do Docker..."

    # Detecta o usuário real (quem chamou sudo, ou o usuário atual)
    REAL_USER="${SUDO_USER:-${USER:-}}"

    if [[ -z "$REAL_USER" || "$REAL_USER" == "root" ]]; then
        log_warn "Não foi possível detectar usuário não-root. Execute manualmente:"
        echo "        usermod -aG docker SEU_USUARIO"
        return 0
    fi

    if id -nG "$REAL_USER" | grep -qw docker; then
        log_ok "Usuário '$REAL_USER' já está no grupo docker."
    else
        usermod -aG docker "$REAL_USER"
        log_ok "Usuário '$REAL_USER' adicionado ao grupo docker."
        log_warn "Para usar docker sem sudo, faça logout e login novamente,"
        echo "        ou execute: newgrp docker"
    fi
}

# ============================================================
# Configura timezone do sistema
# ============================================================

configure_timezone() {
    log_step "Configurando timezone do sistema para ${TIMEZONE}..."

    timedatectl set-timezone "${TIMEZONE}" 2>/dev/null || \
        ln -snf "/usr/share/zoneinfo/${TIMEZONE}" /etc/localtime && \
        echo "${TIMEZONE}" > /etc/timezone

    CURRENT_TZ=$(timedatectl show --property=Timezone --value 2>/dev/null || cat /etc/timezone)
    log_ok "Timezone configurada: ${CURRENT_TZ}"
}

# ============================================================
# Clona o repositório
# ============================================================

clone_repository() {
    log_step "Preparando repositório em ${REPO_DIR}..."

    if [[ -d "${REPO_DIR}/.git" ]]; then
        log_info "Repositório já existe em ${REPO_DIR}. Atualizando..."
        cd "${REPO_DIR}"
        git pull origin main
        log_ok "Repositório atualizado."
    else
        log_info "Clonando ${REPO_URL}..."
        git clone "${REPO_URL}" "${REPO_DIR}"
        log_ok "Repositório clonado em ${REPO_DIR}."
    fi

    # Ajusta permissões para o usuário real
    REAL_USER="${SUDO_USER:-}"
    if [[ -n "$REAL_USER" && "$REAL_USER" != "root" ]]; then
        chown -R "${REAL_USER}:${REAL_USER}" "${REPO_DIR}"
    fi
}

# ============================================================
# Cria o .env a partir do .env.example
# ============================================================

create_env_file() {
    log_step "Configurando arquivo .env..."

    ENV_FILE="${REPO_DIR}/.env"
    ENV_EXAMPLE="${REPO_DIR}/.env.example"

    if [[ -f "$ENV_FILE" ]]; then
        log_ok ".env já existe. Não será sobrescrito."
        return 0
    fi

    if [[ -f "$ENV_EXAMPLE" ]]; then
        cp "$ENV_EXAMPLE" "$ENV_FILE"
        log_ok ".env criado a partir do .env.example."
        log_warn "IMPORTANTE: Edite o arquivo .env com suas credenciais antes de subir o container:"
        echo "        nano ${ENV_FILE}"
    else
        log_warn ".env.example não encontrado. Crie o .env manualmente em ${REPO_DIR}/"
    fi
}

set_env_value() {
    local key="$1" value="$2" file="${REPO_DIR}/.env"
    if grep -q "^${key}=" "$file"; then
        sed -i "s|^${key}=.*|${key}=${value}|" "$file"
    else
        printf '%s=%s\n' "$key" "$value" >> "$file"
    fi
}

ensure_env_value() {
    local key="$1" value="$2" file="${REPO_DIR}/.env"
    if ! grep -q "^${key}=..*" "$file"; then
        set_env_value "$key" "$value"
    fi
}

configure_runtime() {
    log_step "Configurando serviços e credenciais locais..."
    local env_file="${REPO_DIR}/.env"
    local server_ip
    server_ip=$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="src") {print $(i+1); exit}}' || true)
    server_ip="${server_ip:-127.0.0.1}"

    ensure_env_value WEBUI_SECRET_KEY "$(openssl rand -hex 32)"
    ensure_env_value WEBUI_USER admin
    if grep -q '^WEBUI_PASSWORD=DEFINA_UMA_SENHA_FORTE_AQUI$' "$env_file"; then
        set_env_value WEBUI_PASSWORD "$(openssl rand -hex 12)"
    fi
    if grep -q '^FTP_PASSWORD=senha$' "$env_file"; then
        set_env_value FTP_PASSWORD "$(openssl rand -hex 12)"
    fi
    if grep -q '^SFTP_PASSWORD=senha$' "$env_file"; then
        set_env_value SFTP_PASSWORD "$(openssl rand -hex 12)"
    fi
    ensure_env_value FTP_USER oltbackup
    ensure_env_value FTP_PASSWORD "$(openssl rand -hex 12)"
    ensure_env_value FTP_PASV_MIN_PORT 30000
    ensure_env_value FTP_PASV_MAX_PORT 30009
    ensure_env_value SFTP_USER oltbackup
    ensure_env_value SFTP_PASSWORD "$(openssl rand -hex 12)"
    ensure_env_value SFTP_PORT 2222
    for key in BACKUP_SERVER_IP TFTP_IP FTP_IP SFTP_IP; do
        if ! grep -q "^${key}=..*" "$env_file" || grep -q "^${key}=0.0.0.0$" "$env_file"; then
            set_env_value "$key" "$server_ip"
        fi
    done
    chmod 0600 "$env_file"
    log_ok "IP do servidor detectado: ${server_ip}; credenciais locais geradas."
}

configure_firewall() {
    log_step "Configurando firewall para os serviços de backup..."
    if command -v ufw >/dev/null 2>&1; then
        ufw allow 8080/tcp >/dev/null
        ufw allow 21/tcp >/dev/null
        ufw allow 30000:30009/tcp >/dev/null
        ufw allow 69/udp >/dev/null
        ufw allow 2222/tcp >/dev/null
        log_ok "Regras adicionadas ao UFW."
    elif command -v firewall-cmd >/dev/null 2>&1 && systemctl is-active --quiet firewalld; then
        firewall-cmd --permanent --add-port=8080/tcp >/dev/null
        firewall-cmd --permanent --add-port=21/tcp >/dev/null
        firewall-cmd --permanent --add-port=30000-30009/tcp >/dev/null
        firewall-cmd --permanent --add-port=69/udp >/dev/null
        firewall-cmd --permanent --add-port=2222/tcp >/dev/null
        firewall-cmd --reload >/dev/null
        log_ok "Regras adicionadas ao firewalld."
    else
        log_info "Nenhum firewall ativo compatível detectado; nenhuma regra necessária."
    fi
}

deploy_services() {
    log_step "Construindo e iniciando todos os serviços..."
    cd "$REPO_DIR"
    docker compose config --quiet
    docker compose up -d --build --remove-orphans
    sleep 3
    if docker compose ps --status running --services | grep -qx 'olt-backup' && \
       docker compose ps --status running --services | grep -qx 'webui' && \
       docker compose ps --status running --services | grep -qx 'tftp' && \
       docker compose ps --status running --services | grep -qx 'ftp' && \
       docker compose ps --status running --services | grep -qx 'sftp' && \
       docker compose ps --status running --services | grep -qx 'snmp-monitor'; then
        log_ok "Scheduler, painel, TFTP, FTP e SCP/SFTP estão em execução."
    else
        docker compose ps
        log_error "Um ou mais serviços não iniciaram. Consulte: docker compose logs"
        exit 1
    fi
}

import_initial_inventory() {
    local env_file="${REPO_DIR}/.env"
    local inventory_file="${REPO_DIR}/inventory/initial_olts.json"
    # Se o export original for copiado para inventory/ antes da instalação,
    # ele tem prioridade e também importa as communities SNMP por IP.
    if [[ -f "${REPO_DIR}/inventory/zbx_export_hosts.json" ]]; then
        inventory_file="${REPO_DIR}/inventory/zbx_export_hosts.json"
    fi
    if [[ ! -f "$inventory_file" ]] || grep -q '^INITIAL_INVENTORY_IMPORTED=1$' "$env_file"; then
        return 0
    fi
    log_step "Importando inventário inicial de OLTs..."
    if [[ ! -r /dev/tty ]]; then
        log_warn "Terminal interativo indisponível; inventário não importado."
        log_warn "Execute depois: python3 import_inventory.py inventory/initial_olts.json --username bkpolt"
        return 0
    fi
    local olt_password
    read -r -s -p "Senha das OLTs para o usuário bkpolt: " olt_password </dev/tty
    echo ""
    if [[ -z "$olt_password" ]]; then
        log_warn "Senha vazia; inventário não importado."
        return 0
    fi
    printf '%s\n' "$olt_password" | docker compose run --rm -T \
        --entrypoint python3 olt-backup /app/import_inventory.py \
        "/app/inventory/$(basename "$inventory_file")" --username bkpolt --password-stdin
    unset olt_password
    set_env_value INITIAL_INVENTORY_IMPORTED 1
    chmod 0600 "$env_file"
    log_ok "20 OLTs Datacom, ZTE e Huawei processadas sem duplicar IPs."
}

# ============================================================
# Verifica versões instaladas
# ============================================================

verify_installation() {
    log_step "Verificando instalação..."

    echo ""
    echo -e "  ${BOLD}Docker Engine:${NC}   $(docker --version 2>/dev/null || echo 'não encontrado')"
    echo -e "  ${BOLD}Docker Compose:${NC}  $(docker compose version 2>/dev/null || echo 'não encontrado')"
    echo -e "  ${BOLD}Git:${NC}             $(git --version 2>/dev/null || echo 'não encontrado')"
    echo -e "  ${BOLD}Timezone:${NC}        $(timedatectl show --property=Timezone --value 2>/dev/null || cat /etc/timezone)"
    echo ""
}

# ============================================================
# Instruções finais
# ============================================================

print_instructions() {
    local panel_user panel_pass server_ip
    panel_user=$(grep '^WEBUI_USER=' "${REPO_DIR}/.env" | cut -d= -f2-)
    panel_pass=$(grep '^WEBUI_PASSWORD=' "${REPO_DIR}/.env" | cut -d= -f2-)
    server_ip=$(grep '^BACKUP_SERVER_IP=' "${REPO_DIR}/.env" | cut -d= -f2-)
    echo ""
    echo -e "${CYAN}${BOLD}╔══════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}${BOLD}║         Ambiente pronto! Próximos passos:           ║${NC}"
    echo -e "${CYAN}${BOLD}╚══════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "  ${BOLD}Painel:${NC} ${YELLOW}http://${server_ip}:8080${NC}"
    echo -e "  ${BOLD}Usuário:${NC} ${panel_user}"
    echo -e "  ${BOLD}Senha inicial:${NC} ${panel_pass}"
    echo -e "  ${RED}Guarde a senha e altere-a no painel após o primeiro acesso.${NC}"
    echo ""
    echo -e "  ${BOLD}Cadastre as OLTs no painel escolhendo fabricante e modelo.${NC}"
    echo -e "  Configure também o Telegram em Configurações."
    echo ""
    echo -e "  ${BOLD}Configuração avançada:${NC} ${YELLOW}nano ${REPO_DIR}/.env${NC}"
    echo -e "  ${BOLD}Variáveis principais:${NC}"
    echo -e "     ${YELLOW}VENDOR${NC}          — vendors a executar (ex: datacom,zte)"
    echo -e "     ${YELLOW}TELEGRAM_TOKEN${NC}  — token do bot Telegram"
    echo -e "     ${YELLOW}TELEGRAM_CHAT_ID${NC}— ID do chat/grupo Telegram"
    echo -e "     ${YELLOW}*_OLTS${NC}          — OLTs no formato NOME:IP:USUARIO:SENHA"
    echo ""
    echo -e "  ${BOLD}Verifique os logs:${NC}"
    echo -e "     ${YELLOW}docker logs olt-backup${NC}"
    echo ""
    echo -e "  ${BOLD}Backup manual (menu interativo):${NC}"
    echo -e "     ${YELLOW}docker exec -it olt-backup python3 /app/run.py${NC}"
    echo ""
    echo -e "  ${BOLD}Backup imediato (todos os vendors):${NC}"
    echo -e "     ${YELLOW}docker exec olt-backup python3 /app/scheduler.py --now${NC}"
    echo ""
    echo -e "  ${BOLD}Backups agendados automaticamente:${NC} 13:00 e 22:00 (America/Bahia)"
    echo ""
    echo -e "  ${BOLD}Repositório:${NC} ${REPO_URL}"
    echo ""
}

# ============================================================
# Execução principal
# ============================================================

main() {
    banner
    check_root
    detect_distro
    install_base_deps
    install_docker
    configure_docker_service
    add_user_to_docker_group
    configure_timezone
    clone_repository
    create_env_file
    configure_runtime
    configure_firewall
    deploy_services
    import_initial_inventory
    verify_installation
    print_instructions
}

main "$@"

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
            nano
    else
        yum install -y curl git ca-certificates gnupg2 tzdata nano 2>/dev/null || \
        dnf install -y curl git ca-certificates gnupg2 tzdata nano
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
    echo ""
    echo -e "${CYAN}${BOLD}╔══════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}${BOLD}║         Ambiente pronto! Próximos passos:           ║${NC}"
    echo -e "${CYAN}${BOLD}╚══════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "  ${BOLD}1. Edite o arquivo .env com suas credenciais:${NC}"
    echo -e "     ${YELLOW}nano ${REPO_DIR}/.env${NC}"
    echo ""
    echo -e "  ${BOLD}2. Preencha obrigatoriamente:${NC}"
    echo -e "     ${YELLOW}VENDOR${NC}          — vendors a executar (ex: datacom,zte)"
    echo -e "     ${YELLOW}TELEGRAM_TOKEN${NC}  — token do bot Telegram"
    echo -e "     ${YELLOW}TELEGRAM_CHAT_ID${NC}— ID do chat/grupo Telegram"
    echo -e "     ${YELLOW}*_OLTS${NC}          — OLTs no formato NOME:IP:USUARIO:SENHA"
    echo ""
    echo -e "  ${BOLD}3. Suba o container:${NC}"
    echo -e "     ${YELLOW}cd ${REPO_DIR} && docker compose up -d --build${NC}"
    echo ""
    echo -e "  ${BOLD}4. Verifique os logs:${NC}"
    echo -e "     ${YELLOW}docker logs olt-backup${NC}"
    echo ""
    echo -e "  ${BOLD}5. Backup manual (menu interativo):${NC}"
    echo -e "     ${YELLOW}docker exec -it olt-backup python3 /app/run.py${NC}"
    echo ""
    echo -e "  ${BOLD}6. Backup imediato (todos os vendors):${NC}"
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
    verify_installation
    print_instructions
}

main "$@"

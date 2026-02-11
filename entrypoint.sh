#!/bin/bash
set -e

# ============================================================
# Entrypoint universal — multi-vendor OLT Backup
#
# A variável VENDOR (definida no .env) controla quais scripts
# serão agendados no cron. Aceita um ou mais vendors separados
# por vírgula. Exemplo: VENDOR=datacom,zte,parks
# ============================================================

# Exporta variáveis de ambiente para o cron poder ler
printenv | grep -v "no_proxy" > /etc/environment

# Horários do cron (podem ser sobrescritos via .env)
CRON_H1="${CRON_HOUR_1:-13}"
CRON_H2="${CRON_HOUR_2:-22}"

# Gera o crontab dinamicamente com base nos vendors selecionados
CRON_FILE="/etc/cron.d/olt-backup"
echo "SHELL=/bin/bash" > "$CRON_FILE"
echo "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin" >> "$CRON_FILE"
echo "" >> "$CRON_FILE"

IFS=',' read -ra VENDORS <<< "${VENDOR:-datacom}"

for V in "${VENDORS[@]}"; do
    V=$(echo "$V" | xargs)  # trim espaços
    SCRIPT="/app/vendors/${V}/backup.py"

    if [ -f "$SCRIPT" ]; then
        echo "0 ${CRON_H1} * * * root cd /app && /usr/local/bin/python3 ${SCRIPT} >> /app/logs/backup_${V}.log 2>&1" >> "$CRON_FILE"
        echo "0 ${CRON_H2} * * * root cd /app && /usr/local/bin/python3 ${SCRIPT} >> /app/logs/backup_${V}.log 2>&1" >> "$CRON_FILE"
        echo "[OK] Vendor '${V}' agendado às ${CRON_H1}:00 e ${CRON_H2}:00"
    else
        echo "[ERRO] Script não encontrado: ${SCRIPT}"
    fi
done

# Linha em branco obrigatória para cron
echo "" >> "$CRON_FILE"

chmod 0644 "$CRON_FILE"
crontab "$CRON_FILE"

# Cria diretórios
mkdir -p /app/logs /app/backups

# Cria log
touch /var/log/cron.log

echo "============================================="
echo "  OLT Backup Docker — Multi-Vendor"
echo "  Vendors: ${VENDOR:-datacom}"
echo "  Horários: ${CRON_H1}:00 e ${CRON_H2}:00 (${TZ})"
echo "  $(date)"
echo "============================================="

# Inicia o cron em foreground
exec cron -f

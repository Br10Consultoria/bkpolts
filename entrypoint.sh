#!/bin/bash
set -e

# ============================================================
# Entrypoint universal — multi-vendor OLT Backup
#
# Inicia o scheduler.py (daemon Python) que:
#   - Lê VENDOR, CRON_HOUR_1, CRON_HOUR_2 e TZ do .env
#   - Executa os backups dos vendors configurados às horas definidas
#   - Recarrega o .env a cada ciclo (sem precisar reiniciar o container)
#
# Para execução manual dentro do container:
#   python3 /app/run.py              # menu interativo
#   python3 /app/run.py --vendor zte # vendor específico
#   python3 /app/scheduler.py --now  # todos os vendors imediatamente
# ============================================================

# Cria diretórios necessários
mkdir -p /app/logs /app/backups

# Exibe banner de inicialização
echo "╔══════════════════════════════════════════════════════╗"
echo "║         OLT Backup Docker — Multi-Vendor            ║"
echo "║         Br10 Consultoria                            ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""
echo "  Vendors   : ${VENDOR:-não definido}"
echo "  Horários  : ${CRON_HOUR_1:-13}:00 e ${CRON_HOUR_2:-22}:00"
echo "  Timezone  : ${TZ:-America/Bahia}"
echo "  Iniciado  : $(date)"
echo ""
echo "  Para backup manual:"
echo "    docker exec olt-backup python3 /app/run.py"
echo "    docker exec olt-backup python3 /app/run.py --vendor zte"
echo "    docker exec olt-backup python3 /app/scheduler.py --now"
echo ""

# Inicia o scheduler Python em foreground
exec python3 /app/scheduler.py

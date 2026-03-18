#!/usr/bin/env python3
"""
scheduler.py — Daemon de agendamento de backup de OLTs

Executa automaticamente os backups dos vendors configurados no .env
nos horários definidos (padrão: 13:00 e 22:00, timezone do .env).

Uso:
  python3 scheduler.py            # inicia o daemon (blocking)
  python3 scheduler.py --now      # executa imediatamente todos os vendors e sai

Variáveis de ambiente relevantes (.env):
  VENDOR        — vendors a executar (ex: datacom,zte,parks)
  CRON_HOUR_1   — primeiro horário (padrão: 13)
  CRON_HOUR_2   — segundo horário  (padrão: 22)
  TZ            — timezone         (padrão: America/Bahia)
"""

import os
import sys
import time
import logging
import argparse
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

# ============================================================
# Configuração de paths
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
ENV_FILE = BASE_DIR / ".env"
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

VENDOR_MAP = {
    "datacom":   ["DATACOM_OLTS"],
    "zte":       ["ZTE_OLTS", "ZTE_TITAN_OLTS"],
    "parks":     ["PARKS_OLTS"],
    "fiberhome": ["FIBERHOME_OLTS"],
    "huawei":    ["HUAWEI_OLTS"],
}

# ============================================================
# Logging
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_DIR / "scheduler.log"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("scheduler")


# ============================================================
# Helpers
# ============================================================

def load_env(env_file: Path) -> dict:
    """Carrega variáveis do .env sem sobrescrever o ambiente atual."""
    env = {}
    if not env_file.exists():
        log.warning(".env não encontrado em %s", env_file)
        return env
    with open(env_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            env[key] = value
    return env


def get_timezone(_env: dict = None) -> ZoneInfo:
    """Retorna sempre America/Bahia — timezone fixo do sistema."""
    return ZoneInfo("America/Bahia")


def get_schedule_hours(env: dict) -> tuple[int, int]:
    """Retorna os dois horários de execução configurados no .env."""
    try:
        h1 = int(env.get("CRON_HOUR_1", "13"))
    except ValueError:
        h1 = 13
    try:
        h2 = int(env.get("CRON_HOUR_2", "22"))
    except ValueError:
        h2 = 22
    return h1, h2


def get_configured_vendors(env: dict) -> list:
    """
    Retorna a lista de vendors a executar.
    Prioridade: variável VENDOR do .env.
    Fallback: detecta automaticamente quais vendors têm OLTs configuradas.
    """
    vendor_raw = env.get("VENDOR", "").strip()
    if vendor_raw:
        vendors = [v.strip() for v in vendor_raw.split(",") if v.strip()]
        # Filtra apenas vendors válidos
        valid = [v for v in vendors if v in VENDOR_MAP]
        if valid:
            return valid

    # Fallback: detecta automaticamente
    configured = []
    for vendor, vars_ in VENDOR_MAP.items():
        for var in vars_:
            raw = env.get(var, "").strip()
            if raw:
                configured.append(vendor)
                break
    return configured


def run_vendor(vendor: str, env: dict) -> int:
    """Executa o script de backup de um vendor e retorna o código de saída."""
    script = BASE_DIR / "vendors" / vendor / "backup.py"
    if not script.exists():
        log.error("Script não encontrado: %s", script)
        return 1

    merged_env = {**os.environ, **env}
    log.info("Iniciando backup: %s", vendor)

    result = subprocess.run(
        [sys.executable, str(script)],
        env=merged_env,
        cwd=str(BASE_DIR),
    )

    if result.returncode == 0:
        log.info("Backup %s concluído com sucesso.", vendor)
    else:
        log.warning("Backup %s finalizado com código %d.", vendor, result.returncode)

    return result.returncode


def run_all_vendors(env: dict):
    """Executa todos os vendors configurados sequencialmente."""
    vendors = get_configured_vendors(env)
    if not vendors:
        log.warning("Nenhum vendor configurado. Verifique o .env.")
        return

    log.info("=== Iniciando ciclo de backup — %d vendor(s): %s ===",
             len(vendors), ", ".join(vendors))

    for vendor in vendors:
        run_vendor(vendor, env)

    log.info("=== Ciclo de backup concluído ===")


# ============================================================
# Scheduler loop
# ============================================================

def scheduler_loop():
    """Loop principal do daemon de agendamento."""
    log.info("╔══════════════════════════════════════════════════════╗")
    log.info("║         OLT Backup Scheduler iniciado               ║")
    log.info("╚══════════════════════════════════════════════════════╝")

    last_run_hour: int | None = None  # evita dupla execução no mesmo horário

    while True:
        # Recarrega .env a cada ciclo para capturar mudanças sem reiniciar
        env = load_env(ENV_FILE)
        tz = get_timezone()
        h1, h2 = get_schedule_hours(env)
        now = datetime.now(tz)
        current_hour = now.hour
        current_minute = now.minute

        # Executa apenas no minuto 0 dos horários configurados
        if current_minute == 0 and current_hour in (h1, h2):
            run_key = (now.date(), current_hour)
            if last_run_hour != run_key:
                log.info("Horário agendado atingido: %02d:00 (%s)", current_hour, tz.key)
                run_all_vendors(env)
                last_run_hour = run_key
        else:
            # Log de status a cada hora cheia para confirmar que o daemon está vivo
            if current_minute == 0:
                log.info("Aguardando próximo horário. Agora: %s | Agendado: %02d:00 e %02d:00 (%s)",
                         now.strftime("%H:%M"), h1, h2, tz.key)

        # Dorme 30 segundos antes de verificar novamente
        time.sleep(30)


# ============================================================
# Entry point
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="OLT Backup Scheduler — daemon de agendamento automático",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:
  python3 scheduler.py            # inicia daemon (blocking)
  python3 scheduler.py --now      # executa todos os vendors imediatamente e sai
  python3 scheduler.py --status   # exibe configuração atual e sai
        """,
    )
    parser.add_argument(
        "--now",
        action="store_true",
        help="Executa todos os vendors imediatamente e encerra",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Exibe configuração atual (vendors, horários, timezone) e encerra",
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Valida o ambiente: testa variáveis .env, Telegram e conectividade Telnet",
    )
    args = parser.parse_args()

    env = load_env(ENV_FILE)
    tz = get_timezone()
    h1, h2 = get_schedule_hours(env)
    vendors = get_configured_vendors(env)

    if args.status:
        print("\n  OLT Backup Scheduler — Status\n")
        print(f"  Timezone  : {tz.key}")
        print(f"  Horários  : {h1:02d}:00 e {h2:02d}:00")
        print(f"  Vendors   : {', '.join(vendors) if vendors else 'nenhum configurado'}")
        print(f"  Hora atual: {datetime.now(tz).strftime('%d/%m/%Y %H:%M:%S')}")
        print()
        sys.exit(0)

    if args.now:
        log.info("Modo --now: executando todos os vendors imediatamente...")
        run_all_vendors(env)
        sys.exit(0)

    # Modo --test
    if args.test:
        test_script = BASE_DIR / "test.py"
        if not test_script.exists():
            log.error("test.py não encontrado em %s", BASE_DIR)
            sys.exit(1)
        merged_env = {**os.environ, **env}
        result = subprocess.run(
            [sys.executable, str(test_script)],
            env=merged_env,
            cwd=str(BASE_DIR),
        )
        sys.exit(result.returncode)

    # Modo daemon
    log.info("Timezone  : %s", tz.key)
    log.info("Horários  : %02d:00 e %02d:00", h1, h2)
    log.info("Vendors   : %s", ", ".join(vendors) if vendors else "nenhum configurado")
    log.info("Hora atual: %s", datetime.now(tz).strftime("%d/%m/%Y %H:%M:%S"))

    try:
        scheduler_loop()
    except KeyboardInterrupt:
        log.info("Scheduler encerrado pelo usuário.")
        sys.exit(0)


if __name__ == "__main__":
    main()

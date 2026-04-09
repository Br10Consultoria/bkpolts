#!/usr/bin/env python3
"""
scheduler.py — Daemon de agendamento de backups de OLT

Executa automaticamente os scripts de backup dos vendors configurados
no .env nos horários definidos (padrão: 13:00 e 22:00, America/Bahia).

Uso:
  python3 scheduler.py            # inicia o daemon (blocking)
  python3 scheduler.py --now      # executa todos os vendors imediatamente
  python3 scheduler.py --status   # exibe timezone, horários e vendors
  python3 scheduler.py --test     # valida ambiente (delega para test.py)
"""

import os
import sys
import time
import logging
import argparse
import subprocess
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

# ============================================================
# Configuração de paths
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
ENV_FILE = BASE_DIR / ".env"
LOG_FILE = BASE_DIR / "logs" / "scheduler.log"

# Mapeamento de vendor → variáveis de OLT no .env
VENDOR_MAP = {
    "datacom":       ["DATACOM_OLTS"],
    "zte":           ["ZTE_OLTS", "ZTE_TITAN_OLTS"],
    "parks":         ["PARKS_OLTS"],
    "fiberhome":     ["FIBERHOME_OLTS"],
    "huawei":        ["HUAWEI_OLTS"],
    "intelbras_g16": ["INTELBRAS_G16_OLTS"],
}

# ============================================================
# Logging
# ============================================================

def setup_logging():
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    fmt = "%(asctime)s | %(levelname)-5s | %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"
    logging.basicConfig(
        level=logging.INFO,
        format=fmt,
        datefmt=datefmt,
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(LOG_FILE, encoding="utf-8"),
        ],
    )
    return logging.getLogger("scheduler")


log = setup_logging()

# ============================================================
# Helpers
# ============================================================

def load_env(env_file: Path) -> dict:
    """Carrega variáveis do arquivo .env."""
    env = {}
    if not env_file.exists():
        return env
    with open(env_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def get_timezone() -> ZoneInfo:
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
    """Retorna lista de vendors que possuem ao menos uma OLT configurada."""
    vendor_str = env.get("VENDOR", "").strip()
    if vendor_str:
        return [v.strip() for v in vendor_str.split(",") if v.strip() in VENDOR_MAP]
    # Detecta automaticamente pelos *_OLTS preenchidos
    return [
        v for v, vars_ in VENDOR_MAP.items()
        if any(env.get(var, "").strip() for var in vars_)
    ]


def run_vendor(vendor: str, env: dict):
    """Executa o script de backup de um vendor."""
    script = BASE_DIR / "vendors" / vendor / "backup.py"
    if not script.exists():
        log.error("Script não encontrado: %s", script)
        return

    log.info("Iniciando backup: %s", vendor.upper())
    merged_env = {**os.environ, **env}
    result = subprocess.run(
        [sys.executable, str(script)],
        env=merged_env,
        cwd=str(BASE_DIR),
    )
    if result.returncode == 0:
        log.info("Backup %s concluído com sucesso", vendor.upper())
    else:
        log.warning("Backup %s encerrou com código %d", vendor.upper(), result.returncode)


def run_all_vendors(env: dict):
    """Executa o backup de todos os vendors configurados."""
    vendors = get_configured_vendors(env)
    if not vendors:
        log.warning("Nenhum vendor configurado no .env")
        return
    log.info("Executando %d vendor(s): %s", len(vendors), ", ".join(vendors))
    for vendor in vendors:
        run_vendor(vendor, env)
    log.info("Ciclo de backup concluído.")


def print_banner(env: dict, tz: ZoneInfo, h1: int, h2: int, vendors: list):
    """Exibe o banner de inicialização."""
    print("╔══════════════════════════════════════════════════════╗")
    print("║         OLT Backup Docker — Multi-Vendor            ║")
    print("║         Br10 Consultoria                            ║")
    print("╚══════════════════════════════════════════════════════╝")
    print()
    print(f"  Vendors   : {', '.join(vendors) if vendors else 'nenhum configurado'}")
    print(f"  Horários  : {h1:02d}:00 e {h2:02d}:00")
    print(f"  Timezone  : America/Bahia (fixo)")
    print(f"  Iniciado  : {datetime.now(tz).strftime('%d/%m/%Y %H:%M:%S')}")
    print()
    print("  Para backup manual:")
    print("    docker exec -it olt-backup python3 /app/run.py")
    print("    docker exec olt-backup python3 /app/run.py --vendor zte")
    print("    docker exec olt-backup python3 /app/scheduler.py --now")
    print("    docker exec -it olt-backup python3 /app/test.py")
    print()


# ============================================================
# Loop principal
# ============================================================

def scheduler_loop():
    """Loop principal do daemon de agendamento."""
    env = load_env(ENV_FILE)
    tz = get_timezone()
    h1, h2 = get_schedule_hours(env)
    vendors = get_configured_vendors(env)

    print_banner(env, tz, h1, h2, vendors)

    log.info("╔══════════════════════════════════════════════════════╗")
    log.info("║         OLT Backup Scheduler iniciado               ║")
    log.info("╚══════════════════════════════════════════════════════╝")

    last_run_key = None  # evita dupla execução no mesmo horário

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
            if last_run_key != run_key:
                log.info("Horário agendado atingido: %02d:00 (%s)", current_hour, tz.key)
                run_all_vendors(env)
                last_run_key = run_key
        else:
            # Log de status a cada hora cheia para confirmar que o daemon está vivo
            if current_minute == 0:
                log.info(
                    "Aguardando próximo horário. Agora: %s | Agendado: %02d:00 e %02d:00 (%s)",
                    now.strftime("%H:%M"), h1, h2, tz.key,
                )

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
  python3 scheduler.py            # inicia o daemon (blocking)
  python3 scheduler.py --now      # executa todos os vendors imediatamente
  python3 scheduler.py --status   # exibe configuração atual
  python3 scheduler.py --test     # valida ambiente (Telegram + Telnet)
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
    scheduler_loop()


if __name__ == "__main__":
    main()

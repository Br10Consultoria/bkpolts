#!/usr/bin/env python3
"""
run.py — CLI interativo para backup manual de OLTs

Uso:
  python3 run.py                  # menu interativo
  python3 run.py --vendor zte     # executa vendor diretamente (sem menu)
  python3 run.py --all            # executa todos os vendors configurados

O script lê o .env automaticamente, detecta quais vendors e OLTs estão
configurados e exibe um menu para seleção antes de executar o backup.
"""

import os
import sys
import subprocess
import argparse
import time
from pathlib import Path

from common.vendors import vendor_labels, vendor_map
from common.job_control import finish_job, is_cancelled, start_job, terminate_process, touch_job

BASE_DIR = Path(__file__).resolve().parent
ENV_FILE = BASE_DIR / ".env"


# Mapeamento de vendor → variáveis de OLT no .env
VENDOR_MAP = vendor_map()
VENDOR_LABELS = vendor_labels()


# ============================================================
# Helpers
# ============================================================

def load_env(env_file: Path) -> dict:
    """Carrega variáveis do arquivo .env sem sobrescrever o ambiente."""
    env = {}
    if not env_file.exists():
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


def count_olts(env: dict, vendor: str) -> int:
    """Conta o total de OLTs configuradas para um vendor."""
    total = 0
    for var in VENDOR_MAP.get(vendor, []):
        raw = env.get(var, "").strip()
        if raw:
            total += len([e for e in raw.split(",") if e.strip()])
    return total


def detect_configured_vendors(env: dict) -> list:
    """Retorna lista de vendors que possuem ao menos uma OLT configurada."""
    return [v for v in VENDOR_MAP if count_olts(env, v) > 0]


def run_vendor(vendor: str, env: dict):
    """Executa o script de backup do vendor especificado."""
    script = BASE_DIR / "vendors" / vendor / "backup.py"
    if not script.exists():
        print(f"\n[ERRO] Script não encontrado: {script}")
        sys.exit(1)

    # Monta ambiente com variáveis do .env + ambiente atual
    merged_env = {**os.environ, **env}

    print(f"\n{'='*56}")
    print(f"  Executando backup: {VENDOR_LABELS.get(vendor, vendor)}")
    print(f"  OLTs configuradas: {count_olts(env, vendor)}")
    print(f"{'='*56}\n")

    job_id = start_job(vendor, source="cli")
    proc = subprocess.Popen(
        [sys.executable, str(script)],
        env=merged_env,
        cwd=str(BASE_DIR),
    )
    try:
        while proc.poll() is None:
            touch_job(vendor, job_id)
            if is_cancelled(vendor):
                print(f"\n[AVISO] Cancelamento solicitado para {vendor}.")
                terminate_process(proc)
                return 130
            time.sleep(1)
        returncode = proc.returncode
    finally:
        finish_job(vendor, job_id)

    if returncode == 0:
        print(f"\n[OK] Backup {vendor} finalizado com sucesso.")
    else:
        print(f"\n[AVISO] Backup {vendor} finalizado com código {returncode}.")

    return returncode


def print_banner():
    print()
    print("╔══════════════════════════════════════════════════════╗")
    print("║         OLT Backup — Multi-Vendor CLI                ║")
    print("║         Br10 Consultoria                             ║")
    print("╚══════════════════════════════════════════════════════╝")
    print()


def interactive_menu(env: dict):
    """Exibe menu interativo e executa o vendor escolhido."""
    print_banner()

    configured = detect_configured_vendors(env)
    all_vendors = list(VENDOR_MAP.keys())

    if not configured:
        print("[AVISO] Nenhum vendor com OLTs configuradas encontrado no .env")
        print("        Configure as variáveis VENDOR_OLTS no arquivo .env\n")
        sys.exit(0)

    print("  Vendors disponíveis (com OLTs configuradas no .env):\n")
    for idx, vendor in enumerate(all_vendors, start=1):
        qtd = count_olts(env, vendor)
        if qtd > 0:
            status = f"✔  {qtd} OLT(s)"
        else:
            status = "✘  sem OLTs configuradas"
        label = VENDOR_LABELS.get(vendor, vendor)
        print(f"  [{idx}] {label:<42} {status}")

    print(f"\n  [A] Executar TODOS os vendors configurados")
    print(f"  [0] Sair\n")

    while True:
        try:
            choice = input("  Selecione uma opção: ").strip().upper()
        except (KeyboardInterrupt, EOFError):
            print("\n\nInterrompido pelo usuário.")
            sys.exit(0)

        if choice == "0":
            print("\n  Saindo...\n")
            sys.exit(0)

        if choice == "A":
            print(f"\n  Executando todos os {len(configured)} vendor(s) configurados...")
            for vendor in configured:
                run_vendor(vendor, env)
            break

        if choice.isdigit():
            idx = int(choice)
            if 1 <= idx <= len(all_vendors):
                vendor = all_vendors[idx - 1]
                if count_olts(env, vendor) == 0:
                    print(f"\n  [AVISO] Vendor '{vendor}' não possui OLTs configuradas no .env.")
                    print("          Configure a variável correspondente e tente novamente.\n")
                    continue
                run_vendor(vendor, env)
                break
            else:
                print(f"  Opção inválida. Digite um número entre 1 e {len(all_vendors)}, A ou 0.\n")
        else:
            print(f"  Opção inválida. Digite um número entre 1 e {len(all_vendors)}, A ou 0.\n")


# ============================================================
# Entry point
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="OLT Backup CLI — executa backup manual por vendor",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:
  python3 run.py                  # menu interativo
  python3 run.py --vendor zte     # executa ZTE diretamente
  python3 run.py --vendor datacom
  python3 run.py --all            # executa todos os vendors configurados
        """,
    )
    parser.add_argument(
        "--vendor",
        choices=list(VENDOR_MAP.keys()),
        metavar="VENDOR",
        help=f"Vendor a executar diretamente. Opções: {', '.join(VENDOR_MAP.keys())}",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Executa todos os vendors que possuem OLTs configuradas no .env",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="Lista os vendors configurados e quantidade de OLTs",
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Valida o ambiente: testa variáveis .env, Telegram e conectividade Telnet de todas as OLTs",
    )
    parser.add_argument(
        "--test-vendor",
        choices=list(VENDOR_MAP.keys()),
        metavar="VENDOR",
        help="Valida o ambiente apenas para um vendor específico",
    )

    args = parser.parse_args()

    # Carrega .env
    env = load_env(ENV_FILE)
    if not env:
        print(f"[AVISO] Arquivo .env não encontrado em {ENV_FILE}")
        print("        Copie .env.example para .env e configure suas credenciais.\n")

    # Modo --test / --test-vendor
    if args.test or args.test_vendor:
        test_script = BASE_DIR / "test.py"
        if not test_script.exists():
            print("[ERRO] test.py não encontrado.")
            sys.exit(1)
        cmd = [sys.executable, str(test_script)]
        if args.test_vendor:
            cmd += ["--vendor", args.test_vendor]
        merged_env = {**os.environ, **load_env(ENV_FILE)}
        result = subprocess.run(cmd, env=merged_env, cwd=str(BASE_DIR))
        sys.exit(result.returncode)

    # Modo --list
    if args.list:
        print_banner()
        print("  Vendors configurados:\n")
        for vendor in VENDOR_MAP:
            qtd = count_olts(env, vendor)
            status = f"{qtd} OLT(s)" if qtd > 0 else "não configurado"
            print(f"  {vendor:<12} {status}")
        print()
        sys.exit(0)

    # Modo --all
    if args.all:
        print_banner()
        configured = detect_configured_vendors(env)
        if not configured:
            print("[AVISO] Nenhum vendor configurado no .env\n")
            sys.exit(0)
        print(f"  Executando {len(configured)} vendor(s) configurados...\n")
        codes = [run_vendor(vendor, env) for vendor in configured]
        sys.exit(1 if any(codes) else 0)

    # Modo --vendor
    if args.vendor:
        env_full = load_env(ENV_FILE)
        sys.exit(run_vendor(args.vendor, env_full))

    # Modo interativo (padrão)
    interactive_menu(env)


if __name__ == "__main__":
    main()

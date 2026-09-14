#!/usr/bin/env python3
"""
test.py — Testes de validação do ambiente OLT Backup

Verifica, antes de confiar no agendamento automático, se:
  1. As variáveis obrigatórias do .env estão preenchidas
  2. O Telegram está configurado e consegue enviar mensagem
  3. Cada OLT responde na porta Telnet (23)
  4. (Opcional) Executa o backup real de um vendor específico

Uso:
  python3 test.py                    # testa tudo (Telegram + Telnet de todas as OLTs)
  python3 test.py --vendor zte       # testa apenas as OLTs ZTE
  python3 test.py --run datacom      # executa o backup real da Datacom agora
  python3 test.py --run all          # executa o backup real de todos os vendors
"""

import os
import sys
import socket
import argparse
import subprocess
from pathlib import Path
from datetime import datetime

from common.vendors import vendor_map

BASE_DIR = Path(__file__).resolve().parent
ENV_FILE = BASE_DIR / ".env"

# Cores
GREEN  = "\033[0;32m"
RED    = "\033[0;31m"
YELLOW = "\033[1;33m"
CYAN   = "\033[0;36m"
BOLD   = "\033[1m"
NC     = "\033[0m"

VENDOR_MAP = vendor_map()

REQUIRED_VARS = {
    "TELEGRAM_TOKEN":   "Token do bot Telegram",
    "TELEGRAM_CHAT_ID": "Chat ID do Telegram",
}

VENDOR_REQUIRED_VARS = {
    "datacom":   ["TFTP_IP", "DATACOM_OLTS"],
    "zte":       ["FTP_IP", "FTP_USER", "FTP_PASSWORD"],
    "parks":     ["FTP_IP", "FTP_USER", "FTP_PASSWORD", "PARKS_OLTS"],
    "fiberhome": ["FTP_IP", "FTP_USER", "FTP_PASSWORD", "FIBERHOME_OLTS"],
    "huawei":    ["FTP_IP", "FTP_USER", "FTP_PASSWORD", "HUAWEI_OLTS"],
    "intelbras_g16": ["INTELBRAS_G16_OLTS"],
}

# ============================================================
# Helpers
# ============================================================

def ok(msg):    print(f"  {GREEN}{BOLD}[OK]{NC}    {msg}")
def fail(msg):  print(f"  {RED}{BOLD}[FALHA]{NC} {msg}")
def warn(msg):  print(f"  {YELLOW}[AVISO]{NC} {msg}")
def info(msg):  print(f"  {CYAN}[INFO]{NC}  {msg}")
def section(title): print(f"\n{CYAN}{BOLD}{'─'*56}\n  {title}\n{'─'*56}{NC}")


def load_env(env_file: Path) -> dict:
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


def parse_olts(env: dict, var: str) -> list:
    raw = env.get(var, "").strip()
    if not raw:
        return []
    olts = []
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        parts = entry.split(":")
        if len(parts) < 4:
            continue
        olts.append({
            "name": parts[0].strip(),
            "ip":   parts[1].strip(),
            "user": parts[2].strip(),
            "password": ":".join(parts[3:]).strip(),
        })
    return olts


# ============================================================
# Testes
# ============================================================

def test_env_vars(env: dict, vendor: str = None) -> bool:
    """Verifica se as variáveis obrigatórias estão preenchidas."""
    section("1. Variáveis de ambiente")
    passed = True

    # Variáveis globais obrigatórias
    for var, desc in REQUIRED_VARS.items():
        val = env.get(var, "").strip()
        if val and val not in ("SEU_TOKEN_AQUI", "SEU_CHAT_ID_AQUI"):
            ok(f"{var} — configurado")
        else:
            fail(f"{var} — NÃO configurado ({desc})")
            passed = False

    # Variáveis do vendor específico
    vendors_to_check = [vendor] if vendor else list(VENDOR_MAP.keys())
    for v in vendors_to_check:
        for var in VENDOR_REQUIRED_VARS.get(v, []):
            val = env.get(var, "").strip()
            if val and val not in ("0.0.0.0", "usuario", "senha", "SENHA"):
                ok(f"{var} — configurado")
            elif val:
                warn(f"{var} — contém valor padrão do .env.example (verifique)")
            else:
                fail(f"{var} — NÃO configurado")
                passed = False

    return passed


def test_telegram(env: dict) -> bool:
    """Envia uma mensagem de teste ao Telegram."""
    section("2. Telegram")

    token = env.get("TELEGRAM_TOKEN", "").strip()
    chat_id = env.get("TELEGRAM_CHAT_ID", "").strip()

    if not token or not chat_id:
        fail("Telegram não configurado — pulando teste")
        return False

    try:
        import requests
        ts = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        msg = (
            f"🧪 *OLT Backup — Teste de Conectividade*\n"
            f"Ambiente validado com sucesso!\n"
            f"Data/Hora: {ts} (America/Bahia)"
        )
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        resp = requests.post(
            url,
            data={"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"},
            timeout=15,
        )
        if resp.status_code == 200:
            ok("Mensagem de teste enviada ao Telegram com sucesso")
            return True
        else:
            fail(f"Telegram retornou erro {resp.status_code}: {resp.text[:200]}")
            return False
    except Exception as exc:
        fail(f"Exceção ao enviar Telegram: {exc}")
        return False


def test_telnet(env: dict, vendor: str = None) -> dict:
    """Testa conectividade Telnet (porta 23) em todas as OLTs configuradas."""
    section("3. Conectividade Telnet (porta 23)")

    results = {"ok": [], "fail": []}
    vendors_to_check = [vendor] if vendor else list(VENDOR_MAP.keys())

    any_olt = False
    for v in vendors_to_check:
        for var in VENDOR_MAP[v]:
            olts = parse_olts(env, var)
            for olt in olts:
                any_olt = True
                name = olt["name"]
                ip   = olt["ip"]
                try:
                    sock = socket.create_connection((ip, 23), timeout=5)
                    sock.close()
                    ok(f"{name} ({ip}) — porta 23 acessível")
                    results["ok"].append(name)
                except socket.timeout:
                    fail(f"{name} ({ip}) — TIMEOUT (sem resposta em 5s)")
                    results["fail"].append(name)
                except ConnectionRefusedError:
                    fail(f"{name} ({ip}) — RECUSADA (porta 23 fechada)")
                    results["fail"].append(name)
                except OSError as exc:
                    fail(f"{name} ({ip}) — ERRO: {exc}")
                    results["fail"].append(name)

    if not any_olt:
        warn("Nenhuma OLT configurada para os vendors selecionados")

    return results


def run_backup(vendor: str, env: dict):
    """Executa o backup real de um vendor."""
    section(f"Executando backup real: {vendor.upper()}")

    script = BASE_DIR / "vendors" / vendor / "backup.py"
    if not script.exists():
        fail(f"Script não encontrado: {script}")
        return 1

    merged_env = {**os.environ, **env}
    info(f"Iniciando {vendor} — os logs e notificações Telegram serão gerados normalmente")
    print()

    result = subprocess.run(
        [sys.executable, str(script)],
        env=merged_env,
        cwd=str(BASE_DIR),
    )

    print()
    if result.returncode == 0:
        ok(f"Backup {vendor} concluído com sucesso (código 0)")
    else:
        warn(f"Backup {vendor} encerrou com código {result.returncode}")

    return result.returncode


def print_summary(env_ok: bool, telegram_ok: bool, telnet: dict):
    section("Resumo")

    total_ok   = len(telnet["ok"])
    total_fail = len(telnet["fail"])

    print(f"  Variáveis .env  : {'OK' if env_ok else 'COM PROBLEMAS'}")
    print(f"  Telegram        : {'OK' if telegram_ok else 'COM PROBLEMAS'}")
    print(f"  Telnet OLTs     : {total_ok} acessíveis / {total_fail} com falha")

    if telnet["fail"]:
        print(f"\n  {RED}OLTs inacessíveis:{NC}")
        for name in telnet["fail"]:
            print(f"    - {name}")

    if env_ok and telegram_ok and total_fail == 0:
        print(f"\n  {GREEN}{BOLD}Ambiente 100% validado — pronto para backup automático!{NC}")
    elif env_ok and telegram_ok and total_ok > 0:
        print(f"\n  {YELLOW}Ambiente parcialmente validado — verifique as OLTs com falha.{NC}")
    else:
        print(f"\n  {RED}Ambiente com problemas — corrija os erros antes de subir o container.{NC}")
    print()


def banner():
    print()
    print(f"{CYAN}{BOLD}╔══════════════════════════════════════════════════════╗{NC}")
    print(f"{CYAN}{BOLD}║         OLT Backup — Validação de Ambiente          ║{NC}")
    print(f"{CYAN}{BOLD}║         Br10 Consultoria                            ║{NC}")
    print(f"{CYAN}{BOLD}╚══════════════════════════════════════════════════════╝{NC}")


# ============================================================
# Entry point
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="OLT Backup — Validação de ambiente e teste de conectividade",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:
  python3 test.py                    # testa Telegram + Telnet de todas as OLTs
  python3 test.py --vendor zte       # testa apenas as OLTs ZTE
  python3 test.py --run datacom      # executa backup real da Datacom agora
  python3 test.py --run zte          # executa backup real da ZTE agora
  python3 test.py --run all          # executa backup real de todos os vendors
        """,
    )
    parser.add_argument(
        "--vendor",
        choices=list(VENDOR_MAP.keys()),
        metavar="VENDOR",
        help="Filtra o teste para um vendor específico",
    )
    parser.add_argument(
        "--run",
        metavar="VENDOR|all",
        help="Executa o backup real de um vendor (ou 'all' para todos)",
    )
    parser.add_argument(
        "--no-telegram",
        action="store_true",
        help="Pula o teste de envio ao Telegram",
    )
    args = parser.parse_args()

    banner()

    # Carrega .env
    env = load_env(ENV_FILE)
    if not env:
        print(f"\n  {RED}[ERRO]{NC} Arquivo .env não encontrado em {ENV_FILE}")
        print("        Execute: cp .env.example .env && nano .env\n")
        sys.exit(1)

    info(f"Arquivo .env carregado — {len(env)} variável(is) encontrada(s)")

    # Modo --run: executa backup real
    if args.run:
        target = args.run.strip().lower()
        if target == "all":
            configured = [v for v in VENDOR_MAP if any(
                parse_olts(env, var) for var in VENDOR_MAP[v]
            )]
            if not configured:
                print(f"\n  {YELLOW}Nenhum vendor com OLTs configuradas.{NC}\n")
                sys.exit(0)
            for v in configured:
                run_backup(v, env)
        elif target in VENDOR_MAP:
            run_backup(target, env)
        else:
            print(f"\n  {RED}[ERRO]{NC} Vendor '{target}' inválido.")
            print(f"        Opções: {', '.join(VENDOR_MAP.keys())}, all\n")
            sys.exit(1)
        sys.exit(0)

    # Modo padrão: validação de ambiente
    env_ok      = test_env_vars(env, args.vendor)
    telegram_ok = False if args.no_telegram else test_telegram(env)
    telnet      = test_telnet(env, args.vendor)

    print_summary(env_ok, telegram_ok, telnet)


if __name__ == "__main__":
    main()

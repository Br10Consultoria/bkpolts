#!/usr/bin/env python3
"""
setup_vendor.py — Configuração interativa de vendors de OLT

Guia o usuário para configurar qualquer vendor passo a passo:
  1. Exibe menu com todos os vendors disponíveis
  2. Mostra quais variáveis precisam ser preenchidas
  3. Solicita os valores interativamente
  4. Salva tudo no .env automaticamente
  5. Oferece executar o backup de teste imediatamente

Uso:
  python3 setup_vendor.py          # menu interativo completo
  python3 setup_vendor.py --show   # mostra configuração atual do .env
"""

import os
import sys
import subprocess
import argparse
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
ENV_FILE = BASE_DIR / ".env"

# Cores
GREEN  = "\033[0;32m"
RED    = "\033[0;31m"
YELLOW = "\033[1;33m"
CYAN   = "\033[0;36m"
BOLD   = "\033[1m"
NC     = "\033[0m"

# ============================================================
# Definição de cada vendor: campos, descrições e exemplos
# ============================================================

VENDORS = {
    "fiberhome": {
        "label":    "Fiberhome",
        "protocol": "Telnet + FTP",
        "descricao": "OLTs Fiberhome (AN5516, AN6000, etc.)",
        "campos_gerais": [
            {
                "var":     "FTP_IP",
                "desc":    "IP do servidor FTP (onde a OLT vai enviar o backup)",
                "exemplo": "192.168.1.100",
            },
            {
                "var":     "FTP_USER",
                "desc":    "Usuário do FTP",
                "exemplo": "ftpuser",
            },
            {
                "var":     "FTP_PASSWORD",
                "desc":    "Senha do FTP",
                "exemplo": "ftppass",
                "senha":   True,
            },
        ],
        "campo_olts": {
            "var":     "FIBERHOME_OLTS",
            "desc":    "OLTs Fiberhome",
            "formato": "NOME:IP:USUARIO:SENHA",
            "exemplo": "FH_OLT1:10.10.10.60:GEPON:senha123",
        },
    },
    "zte": {
        "label":    "ZTE",
        "protocol": "Telnet + FTP",
        "descricao": "OLTs ZTE (C300, C320, C600, etc.)",
        "campos_gerais": [
            {
                "var":     "FTP_IP",
                "desc":    "IP do servidor FTP",
                "exemplo": "192.168.1.100",
            },
            {
                "var":     "FTP_USER",
                "desc":    "Usuário do FTP",
                "exemplo": "ftpuser",
            },
            {
                "var":     "FTP_PASSWORD",
                "desc":    "Senha do FTP",
                "exemplo": "ftppass",
                "senha":   True,
            },
        ],
        "campo_olts": {
            "var":     "ZTE_OLTS",
            "desc":    "OLTs ZTE padrão",
            "formato": "NOME:IP:USUARIO:SENHA",
            "exemplo": "ZTE_OLT1:10.10.10.2:admin:senha123",
        },
        "campo_olts_extra": {
            "var":     "ZTE_TITAN_OLTS",
            "desc":    "OLTs ZTE Titan (opcional)",
            "formato": "NOME:IP:USUARIO:SENHA",
            "exemplo": "ZTE_TITAN1:10.10.10.3:admin:senha123",
        },
    },
    "datacom": {
        "label":    "Datacom",
        "protocol": "Telnet + TFTP",
        "descricao": "OLTs Datacom (DM4610, DM4615, DM4618, etc.)",
        "campos_gerais": [
            {
                "var":     "TFTP_IP",
                "desc":    "IP do servidor TFTP (o serviço 'tftp' deste docker-compose)",
                "exemplo": "192.168.1.100",
            },
            {
                "var":     "DATACOM_BACKUP_DIR",
                "desc":    "Diretório do host compartilhado entre o serviço tftp e este container (em branco = volume Docker nomeado)",
                "exemplo": "",
            },
        ],
        "campo_olts": {
            "var":     "DATACOM_OLTS",
            "desc":    "OLTs Datacom",
            "formato": "NOME:IP:USUARIO:SENHA",
            "exemplo": "DC_OLT1:172.24.25.2:backupolt:senha123",
        },
    },
    "parks": {
        "label":    "Parks",
        "protocol": "Telnet + FTP",
        "descricao": "OLTs Parks (P360, etc.)",
        "campos_gerais": [
            {
                "var":     "FTP_IP",
                "desc":    "IP do servidor FTP",
                "exemplo": "192.168.1.100",
            },
            {
                "var":     "FTP_USER",
                "desc":    "Usuário do FTP",
                "exemplo": "ftpuser",
            },
            {
                "var":     "FTP_PASSWORD",
                "desc":    "Senha do FTP",
                "exemplo": "ftppass",
                "senha":   True,
            },
        ],
        "campo_olts": {
            "var":     "PARKS_OLTS",
            "desc":    "OLTs Parks",
            "formato": "NOME:IP:USUARIO:SENHA",
            "exemplo": "PARKS_OLT1:10.10.10.50:admin:senha123",
        },
    },
    "huawei": {
        "label":    "Huawei",
        "protocol": "Telnet + FTP",
        "descricao": "OLTs Huawei (MA5800, MA5600, etc.)",
        "campos_gerais": [
            {
                "var":     "FTP_IP",
                "desc":    "IP do servidor FTP",
                "exemplo": "192.168.1.100",
            },
            {
                "var":     "FTP_USER",
                "desc":    "Usuário do FTP",
                "exemplo": "ftpuser",
            },
            {
                "var":     "FTP_PASSWORD",
                "desc":    "Senha do FTP",
                "exemplo": "ftppass",
                "senha":   True,
            },
        ],
        "campo_olts": {
            "var":     "HUAWEI_OLTS",
            "desc":    "OLTs Huawei",
            "formato": "NOME:IP:USUARIO:SENHA",
            "exemplo": "HW_OLT1:10.10.10.70:admin:senha123",
        },
    },
    "intelbras_g16": {
        "label":    "Intelbras G16",
        "protocol": "Telnet + FTP/TFTP",
        "descricao": "OLTs Intelbras G16 (prompt GPON#)",
        "campos_gerais": [
            {
                "var":     "INTELBRAS_BACKUP_METHOD",
                "desc":    "Método de backup: ftp, tftp ou local",
                "exemplo": "ftp",
            },
            {
                "var":     "FTP_IP",
                "desc":    "IP do servidor FTP (para método ftp)",
                "exemplo": "192.168.1.100",
            },
            {
                "var":     "FTP_USER",
                "desc":    "Usuário do FTP",
                "exemplo": "ftpuser",
            },
            {
                "var":     "FTP_PASSWORD",
                "desc":    "Senha do FTP",
                "exemplo": "ftppass",
                "senha":   True,
            },
            {
                "var":     "TFTP_IP",
                "desc":    "IP do servidor TFTP (para método tftp)",
                "exemplo": "192.168.1.100",
            },
        ],
        "campo_olts": {
            "var":     "INTELBRAS_G16_OLTS",
            "desc":    "OLTs Intelbras G16",
            "formato": "NOME:IP:USUARIO:SENHA",
            "exemplo": "G16_OLT1:10.10.10.80:admin:senha123",
        },
    },
}

# ============================================================
# Helpers
# ============================================================

def clr(color, text): return f"{color}{text}{NC}"
def ok(msg):   print(f"  {GREEN}{BOLD}[OK]{NC}    {msg}")
def info(msg): print(f"  {CYAN}[INFO]{NC}  {msg}")
def warn(msg): print(f"  {YELLOW}[AVISO]{NC} {msg}")


def load_env() -> dict:
    env = {}
    if not ENV_FILE.exists():
        return env
    with open(ENV_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def save_env(updates: dict):
    """Atualiza ou adiciona variáveis no .env sem apagar o restante."""
    # Lê o arquivo atual
    lines = []
    if ENV_FILE.exists():
        with open(ENV_FILE, encoding="utf-8") as f:
            lines = f.readlines()

    updated_keys = set()
    new_lines = []

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            new_lines.append(line)
            continue
        key = stripped.split("=", 1)[0].strip()
        if key in updates:
            new_lines.append(f"{key}={updates[key]}\n")
            updated_keys.add(key)
        else:
            new_lines.append(line)

    # Adiciona chaves que não existiam
    for key, value in updates.items():
        if key not in updated_keys:
            new_lines.append(f"{key}={value}\n")

    with open(ENV_FILE, "w", encoding="utf-8") as f:
        f.writelines(new_lines)


def input_field(campo: dict, env: dict) -> str:
    """Solicita o valor de um campo ao usuário, mostrando o valor atual."""
    var     = campo["var"]
    desc    = campo["desc"]
    exemplo = campo.get("exemplo", "")
    is_pass = campo.get("senha", False)

    atual = env.get(var, "")
    atual_display = "****" if (is_pass and atual) else (atual or "não configurado")

    print(f"\n  {CYAN}{var}{NC}")
    print(f"  {desc}")
    print(f"  Exemplo : {exemplo}")
    print(f"  Atual   : {atual_display}")

    try:
        novo = input(f"  Novo valor (Enter para manter): ").strip()
    except (KeyboardInterrupt, EOFError):
        print()
        return atual

    return novo if novo else atual


def input_olts(campo: dict, env: dict) -> str:
    """Solicita as OLTs de um vendor, permitindo adicionar várias."""
    var     = campo["var"]
    desc    = campo["desc"]
    fmt     = campo["formato"]
    exemplo = campo["exemplo"]

    atual = env.get(var, "")

    print(f"\n  {CYAN}{var}{NC} — {desc}")
    print(f"  Formato : {fmt}")
    print(f"  Exemplo : {exemplo}")

    if atual:
        olts_atuais = [o.strip() for o in atual.split(",") if o.strip()]
        print(f"\n  OLTs configuradas atualmente ({len(olts_atuais)}):")
        for i, o in enumerate(olts_atuais, 1):
            partes = o.split(":")
            nome = partes[0] if partes else o
            ip   = partes[1] if len(partes) > 1 else "?"
            print(f"    [{i}] {nome} ({ip})")
    else:
        print(f"\n  Nenhuma OLT configurada ainda.")

    print()
    print(f"  {YELLOW}Opções:{NC}")
    print(f"  [A] Adicionar nova OLT")
    print(f"  [S] Substituir todas as OLTs")
    print(f"  [Enter] Manter como está")

    try:
        opcao = input("  Escolha: ").strip().upper()
    except (KeyboardInterrupt, EOFError):
        print()
        return atual

    if opcao == "A":
        olts_lista = [o.strip() for o in atual.split(",") if o.strip()] if atual else []
        while True:
            print(f"\n  Digite a OLT no formato {fmt}")
            print(f"  Exemplo: {exemplo}")
            print(f"  (Enter em branco para parar)")
            try:
                nova = input("  OLT: ").strip()
            except (KeyboardInterrupt, EOFError):
                break
            if not nova:
                break
            partes = nova.split(":")
            if len(partes) < 4:
                warn(f"Formato inválido. Use: {fmt}")
                continue
            olts_lista.append(nova)
            ok(f"OLT adicionada: {partes[0]} ({partes[1]})")
        return ",".join(olts_lista)

    elif opcao == "S":
        olts_lista = []
        print(f"\n  Digite as OLTs uma por linha. Formato: {fmt}")
        print(f"  Exemplo: {exemplo}")
        print(f"  (Enter em branco para finalizar)")
        while True:
            try:
                nova = input(f"  OLT [{len(olts_lista)+1}]: ").strip()
            except (KeyboardInterrupt, EOFError):
                break
            if not nova:
                break
            partes = nova.split(":")
            if len(partes) < 4:
                warn(f"Formato inválido. Use: {fmt}")
                continue
            olts_lista.append(nova)
            ok(f"OLT adicionada: {partes[0]} ({partes[1]})")
        return ",".join(olts_lista)

    return atual


def count_olts_str(valor: str) -> int:
    if not valor:
        return 0
    return len([o for o in valor.split(",") if o.strip()])


def banner():
    print()
    print(clr(CYAN + BOLD, "╔══════════════════════════════════════════════════════╗"))
    print(clr(CYAN + BOLD, "║     OLT Backup — Configuração Interativa de Vendor  ║"))
    print(clr(CYAN + BOLD, "║     Br10 Consultoria                                ║"))
    print(clr(CYAN + BOLD, "╚══════════════════════════════════════════════════════╝"))
    print()


# ============================================================
# Menu principal
# ============================================================

def menu_principal(env: dict) -> str | None:
    """Exibe o menu de seleção de vendor e retorna o escolhido."""
    print(clr(CYAN + BOLD, "  Vendors disponíveis:\n"))

    vendor_keys = list(VENDORS.keys())
    for i, key in enumerate(vendor_keys, 1):
        v = VENDORS[key]
        # Conta OLTs configuradas
        qtd = count_olts_str(env.get(v["campo_olts"]["var"], ""))
        extra = v.get("campo_olts_extra")
        if extra:
            qtd += count_olts_str(env.get(extra["var"], ""))

        status = f"{GREEN}✔  {qtd} OLT(s){NC}" if qtd > 0 else f"{YELLOW}✘  não configurado{NC}"
        print(f"  [{i}] {v['label']:<12} {v['protocol']:<20} {status}")

    print()
    print(f"  [0] Sair")
    print()

    try:
        escolha = input("  Selecione o vendor: ").strip()
    except (KeyboardInterrupt, EOFError):
        print()
        return None

    if escolha == "0":
        return None

    try:
        idx = int(escolha) - 1
        if 0 <= idx < len(vendor_keys):
            return vendor_keys[idx]
    except ValueError:
        pass

    warn("Opção inválida.")
    return None


def configurar_vendor(vendor_key: str, env: dict):
    """Guia o usuário para configurar um vendor completo."""
    v = VENDORS[vendor_key]
    updates = {}

    print()
    print(clr(CYAN + BOLD, f"  ── Configurando: {v['label']} ({v['descricao']}) ──"))

    # ── Telegram (sempre) ──────────────────────────────────
    print(clr(BOLD, "\n  Credenciais do Telegram"))
    for campo in [
        {"var": "TELEGRAM_TOKEN",   "desc": "Token do bot Telegram", "exemplo": "123456:ABCdef...", "senha": True},
        {"var": "TELEGRAM_CHAT_ID", "desc": "Chat ID do Telegram",   "exemplo": "-100123456789"},
    ]:
        val = input_field(campo, env)
        if val:
            updates[campo["var"]] = val

    # ── Campos gerais do vendor ────────────────────────────
    print(clr(BOLD, f"\n  Configurações de transferência ({v['protocol']})"))
    for campo in v["campos_gerais"]:
        val = input_field(campo, env)
        if val:
            updates[campo["var"]] = val

    # ── OLTs principais ────────────────────────────────────
    print(clr(BOLD, f"\n  OLTs {v['label']}"))
    val = input_olts(v["campo_olts"], env)
    if val is not None:
        updates[v["campo_olts"]["var"]] = val

    # ── OLTs extras (ZTE Titan) ────────────────────────────
    if "campo_olts_extra" in v:
        print(clr(BOLD, f"\n  OLTs {v['label']} Titan (opcional)"))
        val = input_olts(v["campo_olts_extra"], env)
        if val is not None:
            updates[v["campo_olts_extra"]["var"]] = val

    # ── Atualiza VENDOR no .env ────────────────────────────
    vendor_atual = env.get("VENDOR", "")
    vendors_lista = [x.strip() for x in vendor_atual.split(",") if x.strip()] if vendor_atual else []
    if vendor_key not in vendors_lista:
        vendors_lista.append(vendor_key)
        updates["VENDOR"] = ",".join(vendors_lista)

    # ── Salva no .env ──────────────────────────────────────
    if updates:
        save_env(updates)
        print()
        ok(f".env atualizado com {len(updates)} variável(is)")
    else:
        print()
        info("Nenhuma alteração realizada.")

    # ── Pergunta se quer testar agora ─────────────────────
    print()
    print(f"  {YELLOW}Deseja executar o backup de teste agora?{NC}")
    print(f"  [1] Sim — validar ambiente (Telegram + Telnet)")
    print(f"  [2] Sim — executar backup real agora")
    print(f"  [0] Não")
    print()

    try:
        opcao = input("  Escolha: ").strip()
    except (KeyboardInterrupt, EOFError):
        print()
        return

    test_script = BASE_DIR / "test.py"
    merged_env = {**os.environ, **load_env()}

    if opcao == "1":
        print()
        subprocess.run(
            [sys.executable, str(test_script), "--vendor", vendor_key],
            env=merged_env,
            cwd=str(BASE_DIR),
        )
    elif opcao == "2":
        print()
        subprocess.run(
            [sys.executable, str(test_script), "--run", vendor_key],
            env=merged_env,
            cwd=str(BASE_DIR),
        )


def show_config(env: dict):
    """Exibe a configuração atual de todos os vendors."""
    print()
    print(clr(CYAN + BOLD, "  Configuração atual do .env\n"))

    # Telegram
    token   = env.get("TELEGRAM_TOKEN", "")
    chat_id = env.get("TELEGRAM_CHAT_ID", "")
    print(f"  {'TELEGRAM_TOKEN':<22} {'configurado' if token else clr(RED, 'não configurado')}")
    print(f"  {'TELEGRAM_CHAT_ID':<22} {'configurado' if chat_id else clr(RED, 'não configurado')}")
    print()

    # FTP / TFTP (Datacom + Intelbras G16)
    for var in ["FTP_IP", "FTP_USER", "FTP_PASSWORD", "TFTP_IP", "DATACOM_BACKUP_DIR"]:
        val = env.get(var, "")
        display = "****" if ("PASSWORD" in var and val) else (val or clr(RED, "não configurado"))
        print(f"  {var:<22} {display}")
    print()

    # Vendors
    print(f"  {'Vendor':<14} {'OLTs configuradas'}")
    print(f"  {'──────':<14} {'─────────────────'}")
    for key, v in VENDORS.items():
        qtd = count_olts_str(env.get(v["campo_olts"]["var"], ""))
        extra = v.get("campo_olts_extra")
        if extra:
            qtd += count_olts_str(env.get(extra["var"], ""))
        status = f"{GREEN}{qtd} OLT(s){NC}" if qtd > 0 else clr(YELLOW, "não configurado")
        print(f"  {v['label']:<14} {status}")
    print()


# ============================================================
# Entry point
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="OLT Backup — Configuração interativa de vendors",
    )
    parser.add_argument(
        "--show",
        action="store_true",
        help="Exibe a configuração atual do .env e encerra",
    )
    args = parser.parse_args()

    banner()

    # Garante que o .env existe
    if not ENV_FILE.exists():
        exemplo = BASE_DIR / ".env.example"
        if exemplo.exists():
            import shutil
            shutil.copy(exemplo, ENV_FILE)
            ok(f".env criado a partir do .env.example")
        else:
            ENV_FILE.touch()
            ok(f".env criado (vazio)")

    env = load_env()

    if args.show:
        show_config(env)
        return

    while True:
        vendor = menu_principal(env)
        if vendor is None:
            print(f"\n  {GREEN}Até mais!{NC}\n")
            break

        env = load_env()  # recarrega após possíveis edições
        configurar_vendor(vendor, env)
        env = load_env()  # recarrega após salvar

        print()
        try:
            continuar = input("  Configurar outro vendor? [s/N]: ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            print()
            break
        if continuar != "s":
            print(f"\n  {GREEN}Configuração concluída!{NC}")
            print(f"  Para iniciar o agendamento automático:")
            print(f"    docker compose up -d --build")
            print()
            break


if __name__ == "__main__":
    main()

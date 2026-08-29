#!/usr/bin/env python3
"""
Interface web — cadastro de OLTs e disparo manual de backup por vendor.

Roda como um serviço Docker separado (ver docker-compose.yml, serviço
"webui"), compartilhando o mesmo .env, /app/backups e /app/logs do
container principal (scheduler.py).

Login (usuário/senha) é obrigatório: esta interface exibe/edita
credenciais de OLTs, Telegram e do usuário SSH de backup. Não exponha a
porta diretamente na internet — mantenha atrás de VPN/firewall mesmo
com login habilitado.

Variáveis de ambiente:
  WEBUI_USER        — usuário de login (padrão "admin")
  WEBUI_PASSWORD     — senha de login (defina algo forte antes de subir)
  WEBUI_SECRET_KEY   — chave de sessão Flask (opcional; se ausente, uma
                        chave aleatória é gerada a cada reinício, o que
                        derruba sessões abertas ao reiniciar o container)
  WEBUI_PORT         — porta do servidor (padrão 8080)
"""

import os
import secrets
import subprocess
import sys
import threading
from functools import wraps
from pathlib import Path

from flask import Flask, flash, redirect, render_template, request, session, url_for

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BASE_DIR / ".env"
LOG_DIR = BASE_DIR / "logs"

sys.path.insert(0, str(BASE_DIR))
from common.env_store import (  # noqa: E402
    load_env, save_env, validate_olt_field, validate_olt_password,
    parse_olts_raw, serialize_olts,
)

# Cada vendor pode ter mais de uma lista de OLTs (ex.: ZTE padrão + Titan
# são dois grupos dentro do mesmo vendor/script). Formato:
#   vendor: [(env_var, rótulo da seção), ...]
VENDOR_OLT_VARS = {
    "datacom":       [("DATACOM_OLTS", "Datacom")],
    "zte":           [("ZTE_OLTS", "ZTE padrão"), ("ZTE_TITAN_OLTS", "ZTE Titan")],
    "parks":         [("PARKS_OLTS", "Parks")],
    "fiberhome":     [("FIBERHOME_OLTS", "Fiberhome")],
    "huawei":        [("HUAWEI_OLTS", "Huawei")],
    "intelbras_g16": [("INTELBRAS_G16_OLTS", "Intelbras G16")],
}

VENDOR_SCRIPT = {
    "datacom":       "datacom",
    "zte":           "zte",
    "parks":         "parks",
    "fiberhome":     "fiberhome",
    "huawei":        "huawei",
    "intelbras_g16": "intelbras_g16",
}

VENDOR_LABELS = {
    "datacom":       "Datacom (Telnet + SFTP/SCP)",
    "zte":           "ZTE — padrão + Titan (Telnet + FTP)",
    "parks":         "Parks (Telnet + FTP)",
    "fiberhome":     "Fiberhome (Telnet + FTP)",
    "huawei":        "Huawei (Telnet + FTP)",
    "intelbras_g16": "Intelbras G16 (Telnet + FTP/TFTP)",
}

app = Flask(__name__)
app.secret_key = os.getenv("WEBUI_SECRET_KEY") or secrets.token_hex(32)

# Processos de backup em execução, por chave "vendor" ou "vendor:OLT"
_jobs_lock = threading.Lock()
_running_jobs: dict[str, subprocess.Popen] = {}


# ============================================================
# Auth
# ============================================================

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        env = load_env(ENV_FILE)
        expected_user = env.get("WEBUI_USER", "admin")
        expected_pass = env.get("WEBUI_PASSWORD", "")
        user = request.form.get("username", "")
        password = request.form.get("password", "")

        user_ok = secrets.compare_digest(user, expected_user)
        pass_ok = bool(expected_pass) and secrets.compare_digest(password, expected_pass)

        if user_ok and pass_ok:
            session.clear()
            session["logged_in"] = True
            session["csrf"] = secrets.token_hex(16)
            next_url = request.args.get("next") or url_for("dashboard")
            return redirect(next_url)

        flash("Usuário ou senha inválidos.", "error")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


def check_csrf():
    token = request.form.get("csrf", "")
    if not token or not secrets.compare_digest(token, session.get("csrf", "")):
        flash("Sessão expirada, tente novamente.", "error")
        return False
    return True


# ============================================================
# Helpers
# ============================================================

def count_olts(env: dict, vendor: str) -> int:
    total = 0
    for var, _label in VENDOR_OLT_VARS[vendor]:
        raw = env.get(var, "").strip()
        total += len([e for e in raw.split(",") if e.strip()])
    return total


def job_key(vendor: str, olt_name: str | None = None) -> str:
    return f"{vendor}:{olt_name}" if olt_name else vendor


def is_running(key: str) -> bool:
    with _jobs_lock:
        proc = _running_jobs.get(key)
        if proc is None:
            return False
        if proc.poll() is None:
            return True
        del _running_jobs[key]
        return False


def start_backup(vendor: str, olt_name: str | None = None) -> bool:
    """Dispara vendors/<script>/backup.py em background. Retorna False se já rodando."""
    key = job_key(vendor, olt_name)
    with _jobs_lock:
        proc = _running_jobs.get(key)
        if proc is not None and proc.poll() is None:
            return False

        script = BASE_DIR / "vendors" / VENDOR_SCRIPT[vendor] / "backup.py"
        env = {**os.environ, **load_env(ENV_FILE)}
        if olt_name:
            env["OLT_ONLY"] = olt_name
        else:
            env.pop("OLT_ONLY", None)

        proc = subprocess.Popen(
            [sys.executable, str(script)],
            env=env,
            cwd=str(BASE_DIR),
        )
        _running_jobs[key] = proc
    return True


def tail_log(vendor: str, lines: int = 60) -> str:
    script_vendor = VENDOR_SCRIPT.get(vendor, vendor)
    log_file = LOG_DIR / f"backup_{script_vendor}.log"
    if not log_file.exists():
        return "(sem logs ainda — rode um backup primeiro)"
    with open(log_file, encoding="utf-8", errors="replace") as f:
        content = f.readlines()
    return "".join(content[-lines:])


# ============================================================
# Rotas
# ============================================================

@app.route("/")
@login_required
def dashboard():
    env = load_env(ENV_FILE)
    vendors = [
        {
            "key": key,
            "label": VENDOR_LABELS[key],
            "count": count_olts(env, key),
            "running": is_running(key),
        }
        for key in VENDOR_OLT_VARS
    ]
    telegram_ok = bool(env.get("TELEGRAM_TOKEN")) and bool(env.get("TELEGRAM_CHAT_ID"))
    return render_template("dashboard.html", vendors=vendors, telegram_ok=telegram_ok)


@app.route("/vendor/<vendor>")
@login_required
def vendor_page(vendor):
    if vendor not in VENDOR_OLT_VARS:
        flash("Vendor desconhecido.", "error")
        return redirect(url_for("dashboard"))

    env = load_env(ENV_FILE)
    groups = []
    for var, section_label in VENDOR_OLT_VARS[vendor]:
        olts = parse_olts_raw(env.get(var, ""))
        for olt in olts:
            olt["running"] = is_running(job_key(vendor, olt["name"]))
        groups.append({"var": var, "label": section_label, "olts": olts})

    session.setdefault("csrf", secrets.token_hex(16))
    return render_template(
        "vendor.html",
        vendor=vendor,
        label=VENDOR_LABELS[vendor],
        groups=groups,
        vendor_running=is_running(vendor),
        log_text=tail_log(vendor),
        csrf=session["csrf"],
    )


@app.route("/vendor/<vendor>/add", methods=["POST"])
@login_required
def vendor_add(vendor):
    if vendor not in VENDOR_OLT_VARS or not check_csrf():
        return redirect(url_for("vendor_page", vendor=vendor))

    allowed_vars = {var for var, _label in VENDOR_OLT_VARS[vendor]}
    list_var = request.form.get("list_var", "")
    if list_var not in allowed_vars:
        flash("Lista de OLTs inválida.", "error")
        return redirect(url_for("vendor_page", vendor=vendor))

    name = request.form.get("name", "").strip()
    ip = request.form.get("ip", "").strip()
    user = request.form.get("user", "").strip()
    password = request.form.get("password", "")

    for value, label in [(name, "Nome"), (ip, "IP"), (user, "Usuário")]:
        err = validate_olt_field(value, label)
        if err:
            flash(err, "error")
            return redirect(url_for("vendor_page", vendor=vendor))
    err = validate_olt_password(password)
    if err:
        flash(err, "error")
        return redirect(url_for("vendor_page", vendor=vendor))

    env = load_env(ENV_FILE)
    olts = parse_olts_raw(env.get(list_var, ""))
    if any(o["name"] == name for o in olts):
        flash(f"Já existe uma OLT chamada '{name}' nessa lista.", "error")
        return redirect(url_for("vendor_page", vendor=vendor))

    olts.append({"name": name, "ip": ip, "user": user, "password": password})
    save_env(ENV_FILE, {list_var: serialize_olts(olts)})
    flash(f"OLT '{name}' cadastrada.", "success")
    return redirect(url_for("vendor_page", vendor=vendor))


@app.route("/vendor/<vendor>/delete/<name>", methods=["POST"])
@login_required
def vendor_delete(vendor, name):
    if vendor not in VENDOR_OLT_VARS or not check_csrf():
        return redirect(url_for("vendor_page", vendor=vendor))

    allowed_vars = {var for var, _label in VENDOR_OLT_VARS[vendor]}
    list_var = request.form.get("list_var", "")
    if list_var not in allowed_vars:
        flash("Lista de OLTs inválida.", "error")
        return redirect(url_for("vendor_page", vendor=vendor))

    env = load_env(ENV_FILE)
    olts = parse_olts_raw(env.get(list_var, ""))
    remaining = [o for o in olts if o["name"] != name]
    save_env(ENV_FILE, {list_var: serialize_olts(remaining)})
    flash(f"OLT '{name}' removida.", "success")
    return redirect(url_for("vendor_page", vendor=vendor))


@app.route("/vendor/<vendor>/backup", methods=["POST"])
@login_required
def vendor_backup(vendor):
    if vendor not in VENDOR_OLT_VARS or not check_csrf():
        return redirect(url_for("vendor_page", vendor=vendor))

    olt_name = request.form.get("olt_name") or None
    if start_backup(vendor, olt_name):
        alvo = olt_name or "todas as OLTs"
        flash(f"Backup iniciado para {alvo}. Acompanhe pelo log abaixo.", "success")
    else:
        flash("Já existe um backup em execução para esse alvo — aguarde terminar.", "error")
    return redirect(url_for("vendor_page", vendor=vendor))


@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    env = load_env(ENV_FILE)
    session.setdefault("csrf", secrets.token_hex(16))

    if request.method == "POST":
        if not check_csrf():
            return redirect(url_for("settings"))

        updates = {
            "TELEGRAM_TOKEN": request.form.get("telegram_token", "").strip(),
            "TELEGRAM_CHAT_ID": request.form.get("telegram_chat_id", "").strip(),
            "DATACOM_BACKUP_HOST": request.form.get("datacom_backup_host", "").strip(),
            "DATACOM_BACKUP_USER": request.form.get("datacom_backup_user", "").strip(),
            "DATACOM_BACKUP_PATH": request.form.get("datacom_backup_path", "").strip(),
            "DATACOM_COPY_SCHEME": request.form.get("datacom_copy_scheme", "sftp").strip() or "sftp",
            "DATACOM_BACKUP_SFTP_DIR": request.form.get("datacom_backup_sftp_dir", "").strip(),
        }
        new_datacom_pass = request.form.get("datacom_backup_password", "")
        if new_datacom_pass:
            updates["DATACOM_BACKUP_PASSWORD"] = new_datacom_pass

        new_webui_pass = request.form.get("new_webui_password", "").strip()
        if new_webui_pass:
            current = request.form.get("current_webui_password", "")
            if not secrets.compare_digest(current, env.get("WEBUI_PASSWORD", "")):
                flash("Senha atual incorreta — senha do painel não foi alterada.", "error")
                return redirect(url_for("settings"))
            updates["WEBUI_PASSWORD"] = new_webui_pass

        save_env(ENV_FILE, updates)
        flash("Configurações salvas.", "success")
        return redirect(url_for("settings"))

    return render_template("settings.html", env=env, csrf=session["csrf"])


if __name__ == "__main__":
    port = int(os.getenv("WEBUI_PORT", "8080"))
    app.run(host="0.0.0.0", port=port)

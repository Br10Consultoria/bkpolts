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
import json
import secrets
import subprocess
import sys
import threading
import time
from functools import wraps
from pathlib import Path

from flask import Flask, Response, flash, redirect, render_template, request, session, stream_with_context, url_for

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BASE_DIR / ".env"
LOG_DIR = BASE_DIR / "logs"

sys.path.insert(0, str(BASE_DIR))
from common.env_store import (  # noqa: E402
    load_env, save_env, validate_olt_field, validate_olt_name,
    validate_olt_password, parse_olts_raw, serialize_olts,
)
from common.vendors import VENDORS, vendor_labels  # noqa: E402
from common.job_control import (  # noqa: E402
    finish_job, is_cancelled, read_job, request_cancel, start_job, terminate_process, touch_job,
)

# Cada vendor pode ter mais de uma lista de OLTs (ex.: ZTE padrão + Titan
# são dois grupos dentro do mesmo vendor/script). Formato:
#   vendor: [(env_var, rótulo da seção), ...]
VENDOR_OLT_VARS = {
    key: [(model["env_var"], model["label"]) for model in value["models"]]
    for key, value in VENDORS.items()
}

VENDOR_SCRIPT = {key: value["driver"] for key, value in VENDORS.items()}

VENDOR_LABELS = vendor_labels()

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


def is_vendor_busy(vendor: str) -> bool:
    """True se o vendor inteiro OU qualquer OLT dele tiver um backup rodando."""
    if read_job(vendor) or is_running(vendor):
        return True
    with _jobs_lock:
        keys = [k for k in _running_jobs if k.startswith(f"{vendor}:")]
    return any(is_running(k) for k in keys)


def disabled_names(env: dict, list_var: str) -> set[str]:
    return {name.strip() for name in env.get(f"{list_var}_DISABLED", "").split(",") if name.strip()}


def save_disabled(list_var: str, names: set[str]):
    save_env(ENV_FILE, {f"{list_var}_DISABLED": ",".join(sorted(names))})


def _watch_job(vendor: str, key: str, proc: subprocess.Popen, job_id: str):
    """Monitora processo web e atende cancelamento gravado pelo outro container."""
    try:
        while proc.poll() is None:
            touch_job(vendor, job_id)
            if is_cancelled(vendor):
                terminate_process(proc)
                break
            threading.Event().wait(0.5)
    finally:
        finish_job(vendor, job_id)
        with _jobs_lock:
            if _running_jobs.get(key) is proc:
                _running_jobs.pop(key, None)


def start_backup(vendor: str, olt_name: str | None = None) -> bool:
    """Dispara vendors/<script>/backup.py em background. Retorna False se já rodando."""
    key = job_key(vendor, olt_name)
    if is_vendor_busy(vendor):
        return False
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

        job_id = start_job(vendor, source="webui", target=olt_name)
        try:
            proc = subprocess.Popen(
                [sys.executable, str(script)],
                env=env,
                cwd=str(BASE_DIR),
            )
        except Exception:
            finish_job(vendor, job_id)
            raise
        _running_jobs[key] = proc
        threading.Thread(
            target=_watch_job, args=(vendor, key, proc, job_id), daemon=True
        ).start()
    return True


def _pkill_vendor_script(vendor: str) -> bool:
    """Mata, por padrão de linha de comando, qualquer processo rodando o
    backup.py deste vendor NESTE container — cobre casos que o dict
    _running_jobs não sabe sobre: o painel perdeu o rastro (ex.: reiniciou),
    ou o processo foi iniciado via `docker exec ... run.py`/`scheduler.py`
    dentro deste mesmo container. Não alcança OUTRO container (o daemon
    agendado roda em "olt-backup", um container separado com seu próprio
    espaço de processos — para matar algo lá, use
    `docker exec olt-backup pkill -f backup.py`)."""
    script = BASE_DIR / "vendors" / VENDOR_SCRIPT[vendor] / "backup.py"
    try:
        result = subprocess.run(["pkill", "-f", str(script)], capture_output=True)
    except FileNotFoundError:
        log_dir_msg = "pkill não encontrado na imagem — reconstrua com 'docker compose up -d --build'."
        print(log_dir_msg, file=sys.stderr)
        return False
    return result.returncode == 0


def stop_backup(vendor: str, olt_name: str | None = None) -> bool:
    """Encerra um backup em execução. Retorna False se nada foi encontrado
    para matar (nem rastreado, nem por padrão de linha de comando).

    A OLT pode ficar com a sessão Telnet/config pendurada até o próprio
    timeout dela — isso é inerente a interromper no meio, não tem como
    fechar "com educação" um processo que já pode estar travado."""
    key = job_key(vendor, olt_name)
    active = is_vendor_busy(vendor)
    request_cancel(vendor)
    stopped_tracked = False
    with _jobs_lock:
        proc = _running_jobs.get(key)
        if proc is not None and proc.poll() is None:
            terminate_process(proc)
            stopped_tracked = True
        _running_jobs.pop(key, None)

    stopped_pkill = _pkill_vendor_script(vendor)
    return True


def tail_log(vendor: str, lines: int = 60) -> str:
    script_vendor = VENDOR_SCRIPT.get(vendor, vendor)
    log_file = LOG_DIR / f"backup_{script_vendor}.log"
    if not log_file.exists():
        return "(sem logs ainda — rode um backup primeiro)"
    with open(log_file, encoding="utf-8", errors="replace") as f:
        content = f.readlines()
    return "".join(content[-lines:])


def vendor_log_path(vendor: str) -> Path:
    script_vendor = VENDOR_SCRIPT.get(vendor, vendor)
    return LOG_DIR / f"backup_{script_vendor}.log"


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
            "running": is_vendor_busy(key),
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
    shared_job = read_job(vendor)
    groups = []
    for var, section_label in VENDOR_OLT_VARS[vendor]:
        model = next(m for m in VENDORS[vendor]["models"] if m["env_var"] == var)
        olts = parse_olts_raw(env.get(var, ""))
        disabled = disabled_names(env, var)
        for olt in olts:
            olt["enabled"] = olt["name"] not in disabled
            olt["running"] = (
                is_running(job_key(vendor, olt["name"]))
                or bool(shared_job and shared_job.get("target") == olt["name"])
            )
        groups.append({
            "var": var,
            "label": section_label,
            "model": model["key"],
            "protocols": "/".join(p.upper() for p in model["protocols"]),
            "olts": olts,
        })

    session.setdefault("csrf", secrets.token_hex(16))
    return render_template(
        "vendor.html",
        vendor=vendor,
        label=VENDOR_LABELS[vendor],
        groups=groups,
        vendor_running=is_vendor_busy(vendor),
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

    err = validate_olt_name(name)
    if err:
        flash(err, "error")
        return redirect(url_for("vendor_page", vendor=vendor))
    for value, label in [(ip, "IP"), (user, "Usuário")]:
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
    disabled = disabled_names(env, list_var)
    disabled.discard(name)
    save_disabled(list_var, disabled)
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
    disabled = disabled_names(env, list_var)
    disabled.discard(name)
    save_disabled(list_var, disabled)
    flash(f"OLT '{name}' removida.", "success")
    return redirect(url_for("vendor_page", vendor=vendor))


@app.route("/vendor/<vendor>/toggle/<name>", methods=["POST"])
@login_required
def vendor_toggle(vendor, name):
    if vendor not in VENDOR_OLT_VARS or not check_csrf():
        return redirect(url_for("vendor_page", vendor=vendor))
    list_var = request.form.get("list_var", "")
    allowed_vars = {var for var, _label in VENDOR_OLT_VARS[vendor]}
    if list_var not in allowed_vars:
        flash("Modelo inválido.", "error")
        return redirect(url_for("vendor_page", vendor=vendor))
    env = load_env(ENV_FILE)
    if not any(o["name"] == name for o in parse_olts_raw(env.get(list_var, ""))):
        flash("OLT não encontrada.", "error")
        return redirect(url_for("vendor_page", vendor=vendor))
    disabled = disabled_names(env, list_var)
    if name in disabled:
        disabled.remove(name)
        message = f"OLT '{name}' ativada."
    else:
        disabled.add(name)
        message = f"OLT '{name}' desativada; ela será ignorada nos backups."
    save_disabled(list_var, disabled)
    flash(message, "success")
    return redirect(url_for("vendor_page", vendor=vendor))


@app.route("/vendor/<vendor>/edit/<name>", methods=["GET", "POST"])
@login_required
def vendor_edit(vendor, name):
    if vendor not in VENDOR_OLT_VARS:
        return redirect(url_for("dashboard"))
    list_var = request.values.get("list_var", "")
    allowed_vars = {var for var, _label in VENDOR_OLT_VARS[vendor]}
    if list_var not in allowed_vars:
        flash("Modelo inválido.", "error")
        return redirect(url_for("vendor_page", vendor=vendor))
    env = load_env(ENV_FILE)
    olts = parse_olts_raw(env.get(list_var, ""))
    olt = next((o for o in olts if o["name"] == name), None)
    if not olt:
        flash("OLT não encontrada.", "error")
        return redirect(url_for("vendor_page", vendor=vendor))
    session.setdefault("csrf", secrets.token_hex(16))
    if request.method == "GET":
        model_label = dict(VENDOR_OLT_VARS[vendor])[list_var]
        return render_template("olt_edit.html", vendor=vendor, olt=olt,
                               list_var=list_var, model_label=model_label, csrf=session["csrf"])
    if not check_csrf():
        return redirect(url_for("vendor_page", vendor=vendor))
    new_name = request.form.get("name", "").strip()
    ip = request.form.get("ip", "").strip()
    user = request.form.get("user", "").strip()
    password = request.form.get("password", "") or olt["password"]
    errors = [validate_olt_name(new_name)]
    errors.extend(validate_olt_field(value, label) for value, label in [(ip, "IP"), (user, "Usuário")])
    errors.append(validate_olt_password(password))
    error = next((item for item in errors if item), None)
    if error:
        flash(error, "error")
        return redirect(url_for("vendor_edit", vendor=vendor, name=name, list_var=list_var))
    if new_name != name and any(o["name"] == new_name for o in olts):
        flash(f"Já existe uma OLT chamada '{new_name}'.", "error")
        return redirect(url_for("vendor_edit", vendor=vendor, name=name, list_var=list_var))
    index = next(i for i, item in enumerate(olts) if item["name"] == name)
    olts[index] = {"name": new_name, "ip": ip, "user": user, "password": password}
    save_env(ENV_FILE, {list_var: serialize_olts(olts)})
    disabled = disabled_names(env, list_var)
    if name in disabled:
        disabled.remove(name)
        disabled.add(new_name)
        save_disabled(list_var, disabled)
    flash(f"OLT '{new_name}' atualizada.", "success")
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


@app.route("/vendor/<vendor>/stop", methods=["POST"])
@login_required
def vendor_stop(vendor):
    if vendor not in VENDOR_OLT_VARS or not check_csrf():
        return redirect(url_for("vendor_page", vendor=vendor))

    olt_name = request.form.get("olt_name") or None
    if stop_backup(vendor, olt_name):
        flash(
            f"Cancelamento solicitado para {vendor}. O painel, o scheduler e a execução "
            f"manual compartilham esse sinal. A sessão na OLT pode levar alguns segundos "
            f"para encerrar após a interrupção.",
            "success",
        )
    else:
        flash("Não havia backup em execução para esse alvo neste container.", "error")
    return redirect(url_for("vendor_page", vendor=vendor))


@app.route("/vendor/<vendor>/logs/clear", methods=["POST"])
@login_required
def vendor_clear_logs(vendor):
    if vendor not in VENDOR_OLT_VARS or not check_csrf():
        return redirect(url_for("vendor_page", vendor=vendor))

    if is_vendor_busy(vendor):
        flash("Tem um backup rodando agora — espere terminar (ou pare) antes de limpar o log.", "error")
        return redirect(url_for("vendor_page", vendor=vendor))

    script_vendor = VENDOR_SCRIPT.get(vendor, vendor)
    log_file = LOG_DIR / f"backup_{script_vendor}.log"
    log_file.write_text("", encoding="utf-8")
    flash("Log limpo.", "success")
    return redirect(url_for("vendor_page", vendor=vendor))


@app.route("/vendor/<vendor>/logs/stream")
@login_required
def vendor_log_stream(vendor):
    """Entrega somente as novas linhas do log por Server-Sent Events."""
    if vendor not in VENDOR_OLT_VARS:
        return Response(status=404)
    log_file = vendor_log_path(vendor)

    @stream_with_context
    def generate():
        position = log_file.stat().st_size if log_file.exists() else 0
        last_heartbeat = time.monotonic()
        while True:
            try:
                if log_file.exists():
                    size = log_file.stat().st_size
                    if size < position:  # log limpo/rotacionado
                        position = 0
                    if size > position:
                        with open(log_file, encoding="utf-8", errors="replace") as handle:
                            handle.seek(position)
                            chunk = handle.read()
                            position = handle.tell()
                        if chunk:
                            yield f"data: {json.dumps({'text': chunk}, ensure_ascii=False)}\n\n"
                            last_heartbeat = time.monotonic()
                if time.monotonic() - last_heartbeat >= 15:
                    yield ": heartbeat\n\n"
                    last_heartbeat = time.monotonic()
                time.sleep(0.5)
            except GeneratorExit:
                return
            except OSError:
                time.sleep(1)

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


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
            "TFTP_IP": request.form.get("tftp_ip", "").strip(),
            "DATACOM_BACKUP_DIR": request.form.get("datacom_backup_dir", "").strip(),
            "FTP_IP": request.form.get("ftp_ip", "").strip(),
            "FTP_USER": request.form.get("ftp_user", "").strip(),
            "FTP_PASSWORD": request.form.get("ftp_password", ""),
            "SFTP_IP": request.form.get("sftp_ip", "").strip(),
            "SFTP_PORT": request.form.get("sftp_port", "2222").strip(),
            "SFTP_USER": request.form.get("sftp_user", "").strip(),
            "SFTP_PASSWORD": request.form.get("sftp_password", ""),
            "INTELBRAS_BACKUP_METHOD": request.form.get("intelbras_backup_method", "ftp"),
        }
        if updates["INTELBRAS_BACKUP_METHOD"] not in {"ftp", "tftp"}:
            updates["INTELBRAS_BACKUP_METHOD"] = "ftp"

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

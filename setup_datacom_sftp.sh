#!/bin/bash
# ==============================================================
# setup_datacom_sftp.sh — Cria o usuário SFTP/SCP dedicado (chroot)
# que recebe os backups das OLTs Datacom.
#
# Por que isso é um script separado, rodado manualmente com sudo, e não
# algo que a interface web faz sozinha: criar usuários de sistema e
# editar o sshd_config exige root. Dar isso à interface web (que fica
# escutando numa porta de rede) significa que qualquer falha de
# autenticação do painel vira root na máquina. Esse é um risco que não
# vale a pena — por isso esse passo continua manual, uma vez só.
#
# O que este script faz:
#   1. Cria o usuário do sistema (sem shell de login normal)
#   2. Cria a estrutura de diretórios exigida pelo chroot do OpenSSH
#      (a raiz do chroot precisa pertencer a root e não ser gravável
#      pelo próprio usuário — é uma exigência do sshd, não escolha
#      nossa)
#   3. Define a senha do usuário
#   4. Adiciona (ou atualiza) o bloco "Match User" no /etc/ssh/sshd_config
#   5. Valida a sintaxe do sshd_config antes de reiniciar (sshd -t)
#   6. Reinicia o sshd
#
# É idempotente — pode rodar de novo com segurança (ex.: pra trocar a
# senha ou re-aplicar o bloco do sshd_config).
#
# Uso:
#   sudo bash setup_datacom_sftp.sh
#   sudo bash setup_datacom_sftp.sh --user oltbackup --dir /srv/olt-backups
# ==============================================================

set -euo pipefail

SFTP_USER="oltbackup"
CHROOT_DIR="/srv/olt-backups"
UPLOAD_SUBDIR="upload"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --user) SFTP_USER="$2"; shift 2 ;;
        --dir)  CHROOT_DIR="$2"; shift 2 ;;
        *) echo "Argumento desconhecido: $1"; exit 1 ;;
    esac
done

UPLOAD_DIR="${CHROOT_DIR}/${UPLOAD_SUBDIR}"

if [[ $EUID -ne 0 ]]; then
    echo "[ERRO] Rode como root (sudo bash setup_datacom_sftp.sh)."
    exit 1
fi

echo "=============================================================="
echo " Configurando usuário SFTP/SCP dedicado para backups Datacom"
echo "=============================================================="
echo "  Usuário       : ${SFTP_USER}"
echo "  Raiz do chroot: ${CHROOT_DIR}"
echo "  Pasta upload  : ${UPLOAD_DIR}"
echo

# 1. Cria o usuário, se não existir
if id "${SFTP_USER}" &>/dev/null; then
    echo "[OK] Usuário '${SFTP_USER}' já existe."
else
    adduser --disabled-password --gecos "" --home "${CHROOT_DIR}" --shell /usr/sbin/nologin "${SFTP_USER}"
    echo "[OK] Usuário '${SFTP_USER}' criado."
fi

# 2. Estrutura de diretórios exigida pelo chroot do sshd
mkdir -p "${UPLOAD_DIR}"
chown root:root "${CHROOT_DIR}"
chmod 755 "${CHROOT_DIR}"
chown "${SFTP_USER}:${SFTP_USER}" "${UPLOAD_DIR}"
chmod 700 "${UPLOAD_DIR}"
echo "[OK] Diretórios criados/ajustados."

# 3. Senha do usuário
echo
echo "Defina a senha do usuário '${SFTP_USER}' (a mesma vai em"
echo "DATACOM_BACKUP_PASSWORD no .env / na interface web):"
passwd "${SFTP_USER}"

# 4. Bloco Match User no sshd_config (idempotente)
SSHD_CONFIG="/etc/ssh/sshd_config"
MARKER_START="# >>> olt-backup datacom sftp (${SFTP_USER}) >>>"
MARKER_END="# <<< olt-backup datacom sftp (${SFTP_USER}) <<<"

if grep -qF "${MARKER_START}" "${SSHD_CONFIG}" 2>/dev/null; then
    echo "[INFO] Removendo bloco anterior para recriar atualizado..."
    sed -i "/${MARKER_START//\//\\/}/,/${MARKER_END//\//\\/}/d" "${SSHD_CONFIG}"
fi

cat >> "${SSHD_CONFIG}" <<EOF

${MARKER_START}
Match User ${SFTP_USER}
    ChrootDirectory ${CHROOT_DIR}
    ForceCommand internal-sftp
    PasswordAuthentication yes
    AllowTcpForwarding no
    X11Forwarding no
${MARKER_END}
EOF
echo "[OK] Bloco Match User adicionado a ${SSHD_CONFIG}."

# 5. Valida sintaxe antes de reiniciar (evita derrubar o SSH da máquina)
if ! sshd -t; then
    echo "[ERRO] sshd_config inválido após a alteração — revertendo bloco adicionado."
    sed -i "/${MARKER_START//\//\\/}/,/${MARKER_END//\//\\/}/d" "${SSHD_CONFIG}"
    exit 1
fi

# 6. Reinicia o sshd
if systemctl restart sshd 2>/dev/null || systemctl restart ssh 2>/dev/null; then
    echo "[OK] sshd reiniciado."
else
    echo "[AVISO] Não consegui reiniciar automaticamente — reinicie manualmente:"
    echo "        sudo systemctl restart sshd   (ou 'ssh', conforme a distro)"
fi

echo
echo "=============================================================="
echo " Concluído. No .env (ou na interface web, em Configurações):"
echo "   DATACOM_BACKUP_HOST=<IP deste servidor>"
echo "   DATACOM_BACKUP_USER=${SFTP_USER}"
echo "   DATACOM_BACKUP_PASSWORD=<a senha definida acima>"
echo "   DATACOM_BACKUP_SFTP_DIR=${UPLOAD_DIR}"
echo "=============================================================="

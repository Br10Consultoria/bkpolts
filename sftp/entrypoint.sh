#!/bin/sh
set -eu

: "${SFTP_USER:?SFTP_USER não configurado}"
: "${SFTP_PASSWORD:?SFTP_PASSWORD não configurado}"

id "$SFTP_USER" >/dev/null 2>&1 || useradd -d /srv/backups -s /bin/sh "$SFTP_USER"
echo "$SFTP_USER:$SFTP_PASSWORD" | chpasswd
mkdir -p /srv/backups
chmod 0777 /srv/backups
mkdir -p /ssh-keys
if [ ! -f /ssh-keys/ssh_host_ed25519_key ]; then
    ssh-keygen -q -t ed25519 -N '' -f /ssh-keys/ssh_host_ed25519_key
fi

exec /usr/sbin/sshd -D -e -p "${SFTP_PORT:-2222}" \
    -h /ssh-keys/ssh_host_ed25519_key \
    -o PasswordAuthentication=yes \
    -o PermitRootLogin=no \
    -o AllowTcpForwarding=no \
    -o X11Forwarding=no

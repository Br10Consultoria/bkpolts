#!/bin/sh
set -eu

: "${FTP_USER:?FTP_USER não configurado}"
: "${FTP_PASSWORD:?FTP_PASSWORD não configurado}"

id "$FTP_USER" >/dev/null 2>&1 || useradd -d /srv/backups -s /usr/sbin/nologin "$FTP_USER"
echo "$FTP_USER:$FTP_PASSWORD" | chpasswd
mkdir -p /srv/backups
chmod 0777 /srv/backups

cat >/etc/vsftpd.conf <<EOF
listen=YES
listen_ipv6=NO
anonymous_enable=NO
local_enable=YES
write_enable=YES
local_umask=022
chroot_local_user=YES
allow_writeable_chroot=YES
local_root=/srv/backups
pasv_enable=YES
pasv_min_port=${FTP_PASV_MIN_PORT:-30000}
pasv_max_port=${FTP_PASV_MAX_PORT:-30009}
pasv_address=${BACKUP_SERVER_IP:-127.0.0.1}
seccomp_sandbox=NO
use_localtime=YES
xferlog_enable=YES
log_ftp_protocol=YES
EOF

exec /usr/sbin/vsftpd /etc/vsftpd.conf

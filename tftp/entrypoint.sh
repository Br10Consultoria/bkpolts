#!/bin/sh
set -eu
mkdir -p /srv/tftp
chmod 0777 /srv/tftp
exec /usr/sbin/in.tftpd --foreground --verbose --verbose --user tftpuser \
    --address 0.0.0.0:69 --secure --create /srv/tftp

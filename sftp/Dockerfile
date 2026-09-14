FROM debian:12-slim

RUN apt-get update && apt-get install -y --no-install-recommends openssh-server && \
    rm -rf /var/lib/apt/lists/* && mkdir -p /run/sshd

COPY entrypoint.sh /entrypoint.sh
RUN chmod 0755 /entrypoint.sh

EXPOSE 2222
ENTRYPOINT ["/entrypoint.sh"]

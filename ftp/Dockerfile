FROM debian:12-slim

RUN apt-get update && apt-get install -y --no-install-recommends vsftpd && \
    rm -rf /var/lib/apt/lists/*

COPY entrypoint.sh /entrypoint.sh
RUN chmod 0755 /entrypoint.sh

EXPOSE 21 30000-30009
ENTRYPOINT ["/entrypoint.sh"]

# Servidor TFTP dedicado a receber os backups Datacom.
#
# TFTP usa um controle na porta 69/udp, mas a transferência de dados em si
# acontece numa porta UDP efêmera negociada dinamicamente — isso não
# atravessa o NAT do modo bridge padrão do Docker. Por isso este serviço
# roda com network_mode: host no docker-compose.yml (mesma solução já usada
# pelos outros dois serviços deste projeto para alcançar as OLTs).
FROM debian:12-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends tftpd-hpa && \
    apt-get clean && rm -rf /var/lib/apt/lists/* && \
    useradd --system --no-create-home --shell /usr/sbin/nologin tftpuser

RUN mkdir -p /srv/tftp && chown tftpuser:tftpuser /srv/tftp

EXPOSE 69/udp

# --foreground: modo standalone SEM daemonizar (--listen sozinho solta do
#           foreground — o processo faz fork e o pai sai com código 0, o
#           que derruba o PID 1 do container e gera reinício em loop sem
#           nenhum log, exatamente o sintoma visto em produção).
# --secure: chroot para o diretório informado (sem isso, o cliente poderia
#           requisitar caminhos fora dele).
# --create: permite gravar arquivos novos (sem isso, o tftpd-hpa só
#           sobrescreve arquivos já existentes — e a OLT manda um nome novo
#           a cada backup, com timestamp).
ENTRYPOINT ["/usr/sbin/in.tftpd", "--foreground", "--user", "tftpuser", \
            "--address", "0.0.0.0:69", "--secure", "--create", "/srv/tftp"]

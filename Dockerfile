FROM python:3.11-slim

ENV TZ=America/Bahia
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Pacotes do sistema: tzdata (necessário para zoneinfo do Python) e
# procps (fornece pkill/pgrep, usado pela interface web para garantir que
# o botão "Parar" encerre um backup mesmo que o painel tenha perdido o
# rastro do processo, ex.: após reiniciar o container).
RUN apt-get update && \
    apt-get install -y --no-install-recommends tzdata procps tftp-hpa openssh-client && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Timezone fixo: America/Bahia
RUN ln -snf /usr/share/zoneinfo/America/Bahia /etc/localtime && \
    echo "America/Bahia" > /etc/timezone

WORKDIR /app

# Dependências Python (instaladas na imagem — não dependem do volume)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Cria diretórios necessários (persistidos por volumes nomeados)
RUN mkdir -p /app/logs /app/backups

# Usa python3 diretamente como entrypoint para evitar problema de
# permissão do entrypoint.sh quando a raiz é montada como volume.
# O entrypoint.sh é chamado internamente pelo scheduler.py via banner.
ENTRYPOINT ["python3", "/app/scheduler.py"]

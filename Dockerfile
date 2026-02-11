FROM python:3.11-slim

ENV TZ=America/Bahia
ENV PYTHONUNBUFFERED=1

# Pacotes básicos + cron
RUN apt-get update && \
    apt-get install -y cron tzdata && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependências Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia estrutura inicial (será sobrescrito pelos volumes)
COPY . /app

# ✅ Criar diretórios que o script espera
RUN mkdir -p /app/logs \
             /app/backups \
             /home/inove/backups \
             /home/inove/oltdatacom

# Cron job
COPY cronjob /etc/cron.d/bkpoltinove
RUN chmod 0644 /etc/cron.d/bkpoltinove && \
    crontab /etc/cron.d/bkpoltinove

# Log do cron
RUN touch /var/log/cron.log

CMD ["cron", "-f"]

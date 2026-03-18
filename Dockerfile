FROM python:3.11-slim

ENV TZ=America/Bahia
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Pacotes do sistema: tzdata (necessário para zoneinfo do Python)
RUN apt-get update && \
    apt-get install -y --no-install-recommends tzdata && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Timezone do sistema
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

WORKDIR /app

# Dependências Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia toda a estrutura do projeto
COPY . /app

# Cria diretórios necessários
RUN mkdir -p /app/logs /app/backups

# Permissões
RUN chmod +x /app/entrypoint.sh /app/run.py /app/scheduler.py

ENTRYPOINT ["/app/entrypoint.sh"]

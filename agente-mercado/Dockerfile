FROM python:3.12-slim

WORKDIR /app

# Dependencias del sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

# Instalar dependencias Python
COPY pyproject.toml .
RUN pip install --no-cache-dir .

# Copiar código
COPY . .

# Puerto (Railway inyecta $PORT)
EXPOSE 8000

CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}

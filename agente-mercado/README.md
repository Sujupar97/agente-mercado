# Agente de Mercado

Agente autónomo de trading cuantitativo con IA que opera en exchanges cripto (Binance/Bybit) usando Gemini 2.5 Pro para análisis y el criterio de Kelly para gestión de riesgo.

## Características

- Escanea hasta 500 pares cripto cada 10 minutos
- Enriquece datos con CoinGecko, Etherscan, DeFi Llama, noticias y Reddit
- Estima valor justo usando Gemini 2.5 Pro (100 llamadas/día gratis)
- Detecta ineficiencias (desviación > 8% configurable)
- Position sizing con criterio de Kelly fraccional (0.25x, cap 3%)
- Política "paga por ti mismo o muere" — entra en simulación si no cubre costos
- API REST con JWT para monitoreo y control
- Notificaciones via Telegram

## Requisitos

- Python 3.12+
- Docker y Docker Compose
- API keys (ver .env.example)

## Setup Rápido

```bash
# 1. Clonar y entrar al directorio
cd agente-mercado

# 2. Copiar variables de entorno
cp .env.example .env
# Editar .env con tus API keys

# 3. Levantar PostgreSQL y Redis
docker compose -f docker/docker-compose.yml up -d postgres redis

# 4. Crear entorno virtual e instalar
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# 5. Crear tablas en la BD
python scripts/seed_test_data.py

# 6. Ejecutar en modo SIMULACIÓN
AGENT_MODE=SIMULATION uvicorn app.main:app --reload

# 7. En otra terminal: obtener token y consultar estado
curl -X POST http://localhost:8000/api/v1/token
# Copiar el access_token

curl -H "Authorization: Bearer TU_TOKEN" http://localhost:8000/api/v1/status

# 8. Forzar un ciclo manual
curl -X POST -H "Authorization: Bearer TU_TOKEN" http://localhost:8000/api/v1/cycle
```

## Estructura

```
app/
├── core/          # Loop principal, scheduler, estado
├── markets/       # Ingestión de datos de exchanges (ccxt)
├── data/          # Datos externos (CoinGecko, Etherscan, noticias, Reddit)
├── llm/           # Integración Gemini 2.5 Pro
├── analysis/      # Estimación de probabilidad, detección de ineficiencias
├── risk/          # Criterio de Kelly, risk manager
├── trading/       # Ejecución de órdenes, tracking de posiciones
├── pnl/           # P&L calculator, cost tracker
├── notifications/ # Alertas Telegram
├── api/           # REST API (FastAPI)
└── db/            # Modelos ORM, migraciones
```

## API Endpoints

| Método | Ruta | Auth | Descripción |
|--------|------|------|-------------|
| GET | /api/v1/health | No | Health check |
| POST | /api/v1/token | No | Generar JWT |
| GET | /api/v1/status | JWT | Estado del agente |
| GET | /api/v1/positions | JWT | Posiciones abiertas |
| GET | /api/v1/trades | JWT | Historial de trades |
| GET | /api/v1/signals | JWT | Señales del LLM |
| POST | /api/v1/cycle | JWT | Forzar ciclo manual |
| POST | /api/v1/agent/start | JWT | Iniciar agente |
| POST | /api/v1/agent/stop | JWT | Pausar agente |
| PUT | /api/v1/config | JWT | Cambiar parámetros |

## Gestión de Riesgo

| Parámetro | Default | Descripción |
|-----------|---------|-------------|
| fractional_kelly | 0.25 | 25% del Kelly óptimo |
| max_per_trade_pct | 0.03 | 3% máximo por trade |
| max_daily_loss_pct | 0.05 | 5% pérdida diaria máxima |
| max_weekly_loss_pct | 0.10 | 10% pérdida semanal máxima |
| max_drawdown_pct | 0.15 | 15% drawdown máximo |
| deviation_threshold | 0.08 | 8% desviación mínima |
| min_confidence | 0.60 | 60% confianza mínima |

## Tests

```bash
pytest tests/ -v
```

## Docker (Producción)

```bash
docker compose -f docker/docker-compose.yml up -d
```

# Agente de Mercado — Directrices del Proyecto

## Arquitectura

- **Backend**: FastAPI + PostgreSQL + Redis + OANDA v20 REST API
- **Frontend**: React 19 + Vite 7.3 + TailwindCSS v4 (mobile-first)
- **Broker**: OANDA (demo: `api-fxpractice.oanda.com`, live: `api-fxtrade.oanda.com`)
- **HTTP Client**: httpx (async) para comunicacion con OANDA
- **Instrumentos**: EUR_USD, GBP_USD, USD_JPY, XAU_USD
- **Timeframes**: H1 (primario), H4 (contexto), M1 (entrada — lo más cercano a M2)

## Principios Fundamentales

1. **Senales por REGLAS TECNICAS, no LLM.** Las senales de entrada/salida se generan con patrones de velas y analisis de tendencia (Oliver Velez). El LLM NO genera senales.

2. **LLM solo para analisis post-trade.** Se usa Gemini Flash unicamente para:
   - Lecciones de la bitacora (cada 15 trades cerrados)
   - Reportes de aprendizaje interpretativos
   - Analisis del ciclo de mejora (cada 20 trades cerrados)

3. **ImprovementRules son PERMANENTES e IRREVOCABLES.** Una vez creada por el ciclo de 20 trades, una regla NUNCA se desactiva. Se acumulan con el tiempo.

4. **Aprendizaje INTERPRETIVO, no restrictivo.** Los reportes generan entendimiento del mercado, no reglas rigidas adicionales.

5. **Conexion a broker real.** Todas las ordenes se ejecutan via OANDA API. El sistema se valida viendo las posiciones directamente en la plataforma del broker.

## Estrategias Activas

### s1_pullback_20_up
- **Direccion**: LONG
- **Patron**: Pullback a EMA20 en tendencia alcista
- **Entrada**: Rebote del precio en EMA20 + patron de vela alcista
- **Stop**: Low del patron de entrada
- **TP**: Entry + 2x distancia al stop (R:R minimo 1:2)
- **Timeframes**: H1 (primario), H4 (contexto)

### s2_pullback_20_down
- **Direccion**: SHORT
- **Patron**: Pullback a EMA20 en tendencia bajista
- **Entrada**: Rebote del precio en EMA20 + patron de vela bajista
- **Stop**: High del patron de entrada
- **TP**: Entry - 2x distancia al stop (R:R minimo 1:2)
- **Timeframes**: H1 (primario), H4 (contexto)

## Reglas de Riesgo INVIOLABLES

- **1% del balance** por trade
- **R:R minimo 1:2** (si no hay estructura para 2R, descartar)
- **Maximo 3 trades** abiertos simultaneamente
- **Solo operar** durante Londres (07-16 UTC) y NY Overlap (12-16 UTC)
- **Break-even** a 1R de ganancia
- **Cierre parcial 50%** a 2R
- **Trailing stop** en el resto (low/high de vela previa, solo a favor)
- **Perdida diaria maxima**: 3%
- **Drawdown maximo**: 10% desde peak

## 8 Filtros de Contexto (TODOS deben pasar)

1. [Ciclo #1] Alta concentración de trades perdedores en la ventana de apertura de mercado (11:30 - 12:05 UTC), donde la volatilidad inicial genera falsos pullbacks a la EMA20 que son rápidamente revertidos.

### Para S1 (LONG):
1. `trend_state_H1 == "UP"`
2. `trend_state_H4 != "DOWN"`
3. `price > SMA200` en H1
4. `EMA20 > SMA200` en H1
5. `sma200_slope_H1` in ("UP", "FLAT")
6. `ema20_slope_H1` in ("UP", "FLAT")
7. `ma_state_H1 != "WIDE"`
8. `trap_zone_H1 == false`

### Para S2 (SHORT):
Todo invertido (DOWN, BELOW, etc.)

Si **cualquier** filtro falla → no se busca senal.

## 6 Patrones de Entrada

### Alcistas (S1):
- **BULL_ENGULFING**: vela verde engulfe a roja previa, close > high previo
- **PIN_BAR_ALCISTA**: mecha inferior >= 2x cuerpo, close > low + 0.66 * rango
- **GREEN_OVERPOWERS_RED**: verde despues de roja, rango >= 0.7x rango rojo, close > midpoint

### Bajistas (S2):
- **BEAR_ENGULFING**: espejo de bull engulfing
- **PIN_BAR_BAJISTA**: espejo de pin bar alcista
- **RED_OVERPOWERS_GREEN**: espejo de green overpowers red

## Pipeline de Senales — Multi-Timeframe (Oliver Velez)

### Fase 1: Contexto H1/H4 (cada 15 min)
1. Fetch candles H1 (250) + H4 (250) desde broker
2. Construir MarketState H1 y H4 (con SMA200)
3. Correr 8 filtros de contexto → cachear instrumentos que pasan
4. Resultado: lista de instrumentos "listos" por estrategia

### Fase 2: Entradas M1 (cada 1 min)
1. Para instrumentos listos: Fetch candles M1 (100)
2. Construir MarketState M1 (sin SMA200, solo EMA20 + ATR14)
3. Detectar pullback a EMA20 (retrace >= 20% impulso, |price - EMA20| <= 0.50 ATR)
4. Buscar patron de entrada en ultimas 5 velas M1
5. Si hay patron, calcular stop y verificar R:R >= 2:1
6. Aplicar filtro de improvement rules
7. Generar senal → ejecutar orden en broker

### Fase 3: Gestion de posiciones (cada 30 seg)
- Break-even, parciales, trailing, reconciliacion con broker

## Sesiones de Trading (Forex)

- **Londres**: 07:00-16:00 UTC
- **New York**: 12:00-21:00 UTC
- **Overlap**: 12:00-16:00 UTC (preferida)
- **Tokyo**: 23:00-08:00 UTC
- **Mercado cerrado**: Viernes 21:00 UTC a Domingo 21:00 UTC

## Ciclo de Mejora (20 trades)

- Cada 20 trades cerrados por estrategia → LLM analiza
- Genera 1 regla PERMANENTE e IRREVOCABLE
- Las reglas filtran senales futuras
- Tipos: time_filter, pattern_filter, condition_filter, volume_filter

## Capa del Broker

- `app/broker/base.py`: BrokerInterface (ABC)
- `app/broker/oanda.py`: OANDABroker (implementacion httpx)
- `app/broker/capital.py`: CapitalBroker (implementacion httpx, soporta M5)
- `app/broker/models.py`: Candle, Price, AccountState, BrokerPosition, OrderResult
- Cambiar de demo a live: solo cambiar URL y token en .env

## Endpoints API (nuevos)

- `GET /broker/account` — estado cuenta OANDA
- `GET /broker/positions` — posiciones abiertas
- `GET /broker/sync-status` — comparacion local vs broker
- `POST /broker/sync` — forzar reconciliacion
- `GET /market-state` — estado mercado todos los instrumentos
- `GET /market-state/{instrument}` — detalle un instrumento

## Reglas de Mejora Acumuladas

### s1_pullback_20_up

### s2_pullback_20_down

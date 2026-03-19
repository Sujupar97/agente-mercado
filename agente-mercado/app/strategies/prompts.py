"""Prompts LLM — solo para análisis post-trade y aprendizaje.

Las señales de trading se generan por reglas técnicas (app/signals/),
NO por LLM. Estos prompts solo se usan para:
1. Reportes de aprendizaje interpretativos
2. Lecciones de trades individuales (batch)
3. Análisis del ciclo de mejora de 20 trades
"""

# ═══════════════════════════════════════════════════════════
# PROMPT PARA REPORTES DE APRENDIZAJE
# ═══════════════════════════════════════════════════════════

LEARNING_REPORT_PROMPT = """Eres un analista cuantitativo revisando el rendimiento de una estrategia de trading de criptomonedas llamada "{strategy_name}".

DESCRIPCION DE LA ESTRATEGIA:
{strategy_description}

DATOS DE RENDIMIENTO (ultimos {trades_count} trades):
{trades_data}

ESTADISTICAS GLOBALES:
- Win Rate: {win_rate:.1%}
- Profit Factor: {profit_factor:.2f}
- P&L Total: ${total_pnl:.2f}
- Trades ganadores: {wins} | Trades perdedores: {losses}

RENDIMIENTO POR HORA UTC:
{hourly_data}

RENDIMIENTO POR SIMBOLO:
{symbol_data}

INSTRUCCIONES:
Analiza estos datos y genera un reporte INTERPRETATIVO. NO generes reglas rigidas como "nunca operar a las 3am". En su lugar, genera COMPRENSION que permita tomar mejores decisiones.

Para cada patron que encuentres:
1. Describe el patron
2. Explica POR QUE crees que ocurre
3. Sugiere como aprovechar este conocimiento

Responde en JSON con este schema:
{{
  "narrative": "Texto explicativo de 2-3 parrafos analizando el rendimiento general y tendencias principales",
  "patterns": [
    {{"description": "...", "confidence": 0.0-1.0, "type": "hourly|symbol|direction|general"}}
  ],
  "recommendations": [
    "Sugerencia concreta 1",
    "Sugerencia concreta 2"
  ],
  "status_text": "Texto corto (1-2 oraciones) describiendo como va la estrategia — para mostrar en el dashboard"
}}"""


LESSON_BATCH_PROMPT = """Analiza los siguientes trades cerrados de la estrategia "{strategy_name}" y genera una leccion corta (1-2 oraciones) para cada uno. La leccion debe explicar que se puede aprender de este trade.

TRADES:
{trades_data}

Responde en JSON array con exactamente {count} objetos:
[
  {{"trade_id": 123, "lesson": "Leccion aprendida de este trade..."}}
]"""


# ═══════════════════════════════════════════════════════════
# PROMPT PARA CICLO DE MEJORA DE 20 TRADES
# ═══════════════════════════════════════════════════════════

IMPROVEMENT_ANALYSIS_PROMPT = """Eres un analista técnico profesional de Forex revisando un ciclo de {total_trades} trades de la estrategia "{strategy_name}".

DESCRIPCION DE LA ESTRATEGIA:
{strategy_description}

Tu tarea: Identifica EL PATRON TÉCNICO MÁS RECURRENTE en los trades perdedores que NO aparece (o aparece mucho menos) en los ganadores. Solo UNO — el más claro y accionable.

CAMPOS TÉCNICOS DISPONIBLES EN CADA TRADE:
- EMA20_dist: Distancia del precio a la EMA20, medida en múltiplos de ATR. Valores bajos (0.1-0.3) = pullback profundo cerca de EMA20. Valores altos (>1.0) = lejos de EMA20.
- SMA200_dist: Distancia del precio a la SMA200, medida en múltiplos de ATR. Indica fuerza de la tendencia.
- body: Porcentaje del rango de la vela que es cuerpo (vs mechas). Cuerpos grandes (>60%) = velas decisivas. Cuerpos pequeños (<30%) = indecisión.
- upper_wick: Porcentaje del rango que es mecha superior. Mechas grandes = rechazo de precios altos.
- lower_wick: Porcentaje del rango que es mecha inferior. Mechas grandes = rechazo de precios bajos.
- ATR14: Volatilidad actual medida por ATR de 14 períodos.
- retrace: Porcentaje de retroceso del pullback respecto al impulso previo. 20-50% = pullback saludable. >60% = pullback excesivo.
- R:R: Risk-reward ratio al momento de entrada.

TRADES GANADORES ({wins_count}):
{winners_data}

TRADES PERDEDORES ({losses_count}):
{losers_data}

REGLAS YA EXISTENTES (NO repetir estas):
{existing_rules}

INSTRUCCIONES:
1. COMPARA las métricas técnicas de ganadores vs perdedores. Busca diferencias estadísticas claras:
   - ¿Los perdedores tienen EMA20_dist más alto o más bajo?
   - ¿Los perdedores tienen cuerpos de vela más pequeños (indecisión)?
   - ¿Los perdedores tienen mechas más grandes (rechazo)?
   - ¿Los perdedores están más lejos/cerca de SMA200?
   - ¿Los perdedores tienen retrace% excesivo?
2. El patrón debe ser CUANTIFICABLE con umbrales específicos.
3. PRIORIZA reglas técnicas (ema20_distance_filter, candle_quality_filter, sma200_distance_filter) sobre reglas de hora o sesión.
4. La regla debe ser ESPECÍFICA con umbrales numéricos basados en los datos.

Responde en JSON:
{{
  "pattern_name": "nombre_corto_del_patron",
  "description": "Descripción clara en español de qué patrón técnico se identificó con umbrales",
  "evidence": "Comparación cuantitativa: 'Perdedores promedio EMA20_dist=X vs ganadores=Y'",
  "rule_type": "ema20_distance_filter|candle_quality_filter|sma200_distance_filter|time_filter|pattern_filter|condition_filter|session_filter",
  "condition": {{
    // ema20_distance_filter: {{"min_ema20_distance_atr": 0.05, "max_ema20_distance_atr": 0.80}}
    // candle_quality_filter: {{"min_body_pct": 0.40, "max_upper_wick_pct": 0.40, "max_lower_wick_pct": 0.40}}
    // sma200_distance_filter: {{"min_sma200_distance_atr": 1.0, "max_sma200_distance_atr": 15.0}}
    // time_filter: {{"forbidden_hours": [2, 3, 4]}}
    // pattern_filter: {{"forbidden_patterns": ["PIN_BAR_BAJISTA"]}}
    // condition_filter: {{"min_confidence": 0.60, "forbidden_instruments": ["USD_JPY"]}}
    // session_filter: {{"forbidden_sessions": ["TOKYO"]}}
  }},
  "confidence": 0.0-1.0,
  "expected_improvement": "Estimación cuantitativa del impacto (ej: 'filtraría 5/8 pérdidas manteniendo 6/7 ganadores')"
}}"""

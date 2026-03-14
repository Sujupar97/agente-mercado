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

IMPROVEMENT_ANALYSIS_PROMPT = """Eres un analista de trading revisando un ciclo de {total_trades} trades de la estrategia "{strategy_name}".

DESCRIPCION DE LA ESTRATEGIA:
{strategy_description}

Tu tarea: Identifica EL PATRON MAS RECURRENTE en los trades perdedores que NO aparece (o aparece mucho menos) en los ganadores. Solo UNO — el más claro y accionable.

TRADES GANADORES ({wins_count}):
{winners_data}

TRADES PERDEDORES ({losses_count}):
{losers_data}

REGLAS YA EXISTENTES (NO repetir estas):
{existing_rules}

INSTRUCCIONES:
1. Analiza los trades perdedores buscando patrones comunes (hora, símbolo, patrón técnico, duración, condiciones de mercado).
2. Compara con los ganadores: el patrón debe ser significativamente más frecuente en perdedores.
3. Genera UNA regla técnica evaluable que prevenga este patrón.
4. La regla debe ser ESPECÍFICA y EVALUABLE programáticamente.

Responde en JSON:
{{
  "pattern_name": "nombre_corto_del_patron",
  "description": "Descripción clara en español de qué patrón se identificó",
  "evidence": "X de Y trades perdedores muestran este patrón vs Z de W ganadores",
  "rule_type": "time_filter|pattern_filter|condition_filter|volume_filter",
  "condition": {{
    // Varía según rule_type:
    // time_filter: {{"forbidden_hours": [2, 3, 4]}}
    // pattern_filter: {{"forbidden_patterns": ["narrow_range_bars"]}}
    // condition_filter: {{"min_confidence": 0.60, "forbidden_symbols": ["DOGE/USDT"]}}
    // volume_filter: {{"min_volume_ratio": 1.5}}
  }},
  "confidence": 0.0-1.0,
  "expected_improvement": "Estimación de cuánto mejoraría el win rate si se aplica esta regla"
}}"""

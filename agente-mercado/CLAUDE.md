# Agente de Mercado — Reglas del Proyecto

## Principios Fundamentales

1. **Señales por REGLAS TÉCNICAS, no LLM.** Las señales de entrada/salida se generan con patrones de velas y análisis de tendencia (Oliver Vélez). El LLM NO genera señales.

2. **LLM solo para análisis post-trade.** Se usa Gemini Flash únicamente para:
   - Lecciones de la bitácora (cada 15 trades cerrados)
   - Reportes de aprendizaje interpretativos
   - Análisis del ciclo de mejora (cada 20 trades cerrados)

3. **ImprovementRules son PERMANENTES e IRREVOCABLES.** Una vez creada por el ciclo de 20 trades, una regla NUNCA se desactiva. Se acumulan con el tiempo.

4. **Aprendizaje INTERPRETIVO, no restrictivo.** Los reportes generan entendimiento del mercado, no reglas rígidas adicionales. Las únicas reglas automáticas vienen del ciclo de mejora.

5. **Simulación continua.** El agente opera 24/7 en modo SIMULATION con $50 por estrategia. El modo SHUTDOWN nunca se activa en simulación.

## Estrategias Activas

### oliver_elephant
- **Patrón**: Velas Elefante (cuerpo >= 70% del rango)
- **Entrada**: Ruptura del máximo (BUY) o mínimo (SELL) de la vela elefante
- **Stop**: Extremo opuesto de la vela
- **Timeframes**: Detección en 5m/15m, tendencia en 1h
- **Filtro**: Solo a favor de la tendencia (20/200 SMA)

1. [Ciclo #1] Las Elephant Bars ejecutadas después de las 12:23 UTC muestran una tasa de fallo drásticamente superior, indicando una pérdida de momentum o agotamiento de la volatilidad inicial de la apertura.

2. [Ciclo #2] El uso de un tamaño de posición (size) superior a 2.00 USDT está altamente correlacionado con los trades perdedores, sugiriendo una gestión de riesgo agresiva o una sobreexposición en activos de alta volatilidad que no logran sostener el momentum de la vela elefante.

3. [Ciclo #3] Trades con una duración inferior a 20 minutos presentan una alta tasa de fallo, indicando que la ruptura de la vela elefante carece de seguimiento (follow-through) y se convierte en una trampa de liquidez o un falso rompimiento inmediato.

4. [Ciclo #4] Las operaciones ejecutadas después de las 16:00 UTC muestran una tasa de fallo extremadamente alta, coincidiendo con el cierre de los mercados principales y la falta de volumen institucional para sostener la ruptura de la vela elefante.

5. [Ciclo #5] Trades que superan los 90 minutos de duración sin alcanzar el objetivo de beneficio, lo cual indica una falta de momentum sostenido tras la ruptura inicial de la vela elefante, resultando en un desgaste del trade.

6. [Ciclo #6] Concentración excesiva de operaciones en activos de alta volatilidad y baja capitalización (memecoins como DOGE, PENGU, ROBO, TRUMP) que presentan una alta tasa de falsos rompimientos en la estrategia de vela elefante.

7. [Ciclo #7] Concentración de operaciones en ventanas temporales específicas (13:38, 13:53 y 14:13 UTC) donde la volatilidad de apertura ya se ha disipado, provocando una alta tasa de falsos rompimientos.

8. [Ciclo #8] Las entradas ejecutadas a partir de las 14:58 UTC presentan una alta tasa de fallo, ya que coinciden con el agotamiento del impulso inicial de la apertura y una mayor probabilidad de reversión o estancamiento, a diferencia de los trades ganadores que se concentran mayoritariamente antes de las 14:50 UTC.

9. [Ciclo #9] Ejecución de múltiples trades de 'Vela Elefante' en un rango de tiempo muy estrecho (00:08 - 00:33 UTC) durante la apertura asiática, donde la alta frecuencia de entradas sugiere una sobreoperación en un mercado que aún no ha definido una tendencia clara, resultando en múltiples trampas de liquidez consecutivas.

10. [Ciclo #11] Concentración de trades perdedores durante la apertura asiática (00:00 - 03:00 UTC), donde la falta de liquidez institucional y la baja direccionalidad provocan que las velas elefante actúen como trampas de liquidez en lugar de rupturas tendenciales.

### oliver_sma
- **Patrón**: Pullback a SMA 20 en tendencia establecida
- **Entrada**: Rebote del precio en SMA 20
- **Stop**: Debajo/arriba de SMA 20
- **Timeframes**: Detección en 15m/1h, tendencia en 1h
- **Filtro**: Requiere tendencia BULLISH o BEARISH (no NARROW/MIXED)

1. [Ciclo #1] Alta concentración de trades perdedores en la franja horaria de apertura temprana (11:00 - 13:00 UTC), donde la volatilidad inicial suele invalidar los pullbacks a la SMA20 antes de que se establezca una tendencia clara.

2. [Ciclo #2] El uso de un tamaño de posición (size) significativamente mayor (>= 2.70) en los trades perdedores, lo que sugiere un sesgo de revancha o sobreapalancamiento que no está presente en los trades ganadores, donde el tamaño se mantiene constante y conservador (<= 1.84).

3. [Ciclo #3] Ejecución de pullbacks a la SMA20 durante la ventana de tiempo tardía (14:58 - 15:48 UTC), donde la tendencia inicial ya ha perdido fuerza y el mercado entra en una fase de reversión o consolidación, invalidando la continuidad del movimiento.

4. [Ciclo #4] Ejecución de múltiples pullbacks consecutivos sobre el mismo activo en un periodo breve (menos de 30 minutos entre entradas), lo cual indica una falta de paciencia tras un stop loss y una alta probabilidad de estar operando en un rango lateral o agotamiento de tendencia.

5. [Ciclo #5] Ejecución de trades con una duración extremadamente corta (menor a 30 minutos), lo cual indica una entrada impulsiva o 'fomo' en lugar de esperar la confirmación de soporte/resistencia en la SMA20, resultando en stop-losses rápidos por ruido de mercado.

6. [Ciclo #6] Ejecución de trades durante la ventana de baja liquidez nocturna (23:00 - 01:00 UTC), donde la falta de volumen institucional provoca que los pullbacks a la SMA20 sean erráticos y propensos a ser barridos por ruido de mercado.

7. [Ciclo #7] Se observa una correlación directa entre el incremento del tamaño de la posición (size >= 2.65) y la ejecución de trades perdedores, lo cual indica un comportamiento de 'revenge trading' o gestión de riesgo deficiente al aumentar el riesgo tras una pérdida previa, patrón ausente en los trades ganadores donde el tamaño se mantiene constante y conservador.

8. [Ciclo #8] Ejecución de trades en el activo FIL/USDT durante la franja horaria de 17:00 a 21:00 UTC, donde el activo muestra una incapacidad sistemática para respetar la SMA20, sugiriendo una desconexión entre la estrategia y la liquidez específica de este par en dicho horario.

9. [Ciclo #9] Concentración excesiva de operaciones en la ventana horaria de 16:13 a 16:33 UTC, donde la alta volatilidad intradía y el ruido de mercado invalidan sistemáticamente la estrategia de pullback a la SMA20.

10. [Ciclo #10] Ejecución de trades en la franja horaria de 21:00 a 21:45 UTC, donde se observa una alta frecuencia de reversiones bruscas que invalidan el pullback a la SMA20, posiblemente debido al cierre de posiciones institucionales del día.

### oliver_ignored
- **Patrón**: Barras Ignoradas (GREEN-RED-GREEN / RED-GREEN-RED)
- **Entrada**: Ruptura del extremo de la 3ra barra
- **Stop**: Extremo opuesto de la barra ignorada (2da)
- **Timeframes**: Detección en 5m/15m, tendencia en 1h
- **Filtro**: Solo a favor de la tendencia

1. [Ciclo #1] Los trades perdedores presentan una duración excesivamente corta (menor a 10 minutos), lo que indica una entrada prematura en falsas rupturas o falta de confirmación de momentum en la barra ignorada.

2. [Ciclo #2] El patrón identificado es la sobreexposición recurrente al mismo activo (específicamente COS/USDT) en un periodo de tiempo muy concentrado, lo que sugiere una falta de diversificación y una persistencia en operar un activo que ha dejado de presentar momentum válido.

3. [Ciclo #3] Concentración de operaciones de venta (SELL) ejecutadas exactamente a las 13:18 UTC, coincidiendo con un periodo de alta volatilidad errática y reversión rápida, donde la estrategia de barra ignorada falla sistemáticamente.

4. [Ciclo #4] Se observa una correlación directa entre el aumento del tamaño de la posición (size > $2.50) y la alta tasa de fracaso en los trades. Los trades ganadores mantienen un tamaño de posición moderado ($1.34 - $2.01), mientras que los perdedores escalan agresivamente el tamaño, lo que sugiere una gestión de riesgo deficiente o un intento de recuperar pérdidas mediante el aumento del apalancamiento/exposición.

5. [Ciclo #5] Se observa una alta tasa de fracaso en operaciones ejecutadas en la ventana temporal de 15:08 a 15:43 UTC, donde el mercado muestra una reversión rápida o falta de continuación tras la barra ignorada, posiblemente debido a la fatiga de la tendencia principal tras la apertura.

6. [Ciclo #6] Alta tasa de fallos en operaciones ejecutadas en la ventana de tiempo de 15:48 a 16:23 UTC, donde la tendencia principal se agota y el mercado tiende a revertir, invalidando la continuación de la barra ignorada.

7. [Ciclo #7] Se observa una alta tasa de fracaso en operaciones ejecutadas a las 18:23 UTC, donde la tendencia principal pierde fuerza y la probabilidad de continuación tras la barra ignorada disminuye drásticamente en comparación con las horas de mayor liquidez.

8. [Ciclo #8] Se observa una alta tasa de fracaso en operaciones de venta (SELL) ejecutadas específicamente a las 05:18 UTC, donde el mercado tiende a mostrar una reversión alcista o falta de continuación bajista, invalidando la estrategia de barra ignorada en esa ventana temporal.

9. [Ciclo #9] Se observa una alta tasa de fallos cuando se ejecutan múltiples operaciones del mismo activo en un intervalo de tiempo extremadamente corto (menos de 15 minutos), lo que indica una persecución del precio (chasing) en lugar de esperar una nueva configuración válida tras el fallo inicial.

10. [Ciclo #10] Se observa una correlación crítica donde el incremento del tamaño de la posición por encima de $2.50 en activos que ya han mostrado volatilidad errática (NEAR, RESOLV, HUMA) resulta en una tasa de fallo del 100% en este set, indicando un sesgo de 'revancha' o sobreapalancamiento en trades de baja calidad.

10. [Ciclo #11] Se observa una alta tasa de fallos en operaciones ejecutadas simultáneamente a las 14:13 UTC, donde la ejecución masiva de múltiples activos sugiere una entrada mecánica basada en tiempo y no en una confirmación técnica real del momentum tras la barra ignorada.

10. [Ciclo #12] Se observa una alta tasa de fallos en operaciones ejecutadas en la ventana de 14:03 a 14:38 UTC, donde el mercado presenta una alta volatilidad de reversión que invalida la continuación de la barra ignorada, a diferencia de los trades ganadores que se concentran mayoritariamente en la ventana de las 16:47 UTC.

10. [Ciclo #13] Se observa una alta tasa de fallos en operaciones ejecutadas exactamente a las 19:28 UTC, donde múltiples activos (LTC, HUMA, VIRTUAL, FIL, RESOLV, PIXEL) fallan simultáneamente, sugiriendo una entrada mecánica o una trampa de liquidez en ese minuto específico que no se observa en los trades ganadores.

10. [Ciclo #14] Se observa una alta tasa de fallos en operaciones ejecutadas después de las 21:00 UTC, donde la liquidez del mercado disminuye significativamente, provocando que los patrones de 'barra ignorada' no tengan seguimiento y resulten en reversiones rápidas o estancamiento.

10. [Ciclo #15] Se observa una alta tasa de fallos en operaciones ejecutadas durante la ventana de apertura de sesión (00:08 - 00:18 UTC), donde la volatilidad inicial y la falta de consolidación de tendencia provocan que el patrón de barra ignorada falle sistemáticamente al no tener una dirección clara establecida.

10. [Ciclo #16] Alta tasa de fallos en operaciones ejecutadas durante la ventana de apertura de sesión (00:08 - 00:33 UTC), donde la volatilidad inicial y la falta de consolidación de tendencia provocan que el patrón de barra ignorada falle sistemáticamente al no tener una dirección clara establecida.

10. [Ciclo #17] Se observa una alta tasa de fallos al intentar operar el mismo activo inmediatamente después de una operación perdedora (revancha), especialmente notable en activos como FIL, ROBO y KITE, donde se encadenan múltiples entradas fallidas en intervalos cortos.

10. [Ciclo #18] Se identifica una correlación directa entre el aumento del tamaño de la posición a $2.40-$2.42 y la tasa de fracaso. Los trades ganadores utilizan consistentemente un tamaño de $1.08-$1.61, mientras que los perdedores escalan el tamaño de forma agresiva, lo que sugiere una gestión de riesgo deficiente o un sesgo de revancha.

10. [Ciclo #19] Se observa una alta tasa de fallos en operaciones ejecutadas en la ventana de madrugada (02:58 - 04:03 UTC), donde el mercado carece de la liquidez necesaria para confirmar la continuación del momentum tras la barra ignorada, resultando en trades de larga duración con P&L negativo.

10. [Ciclo #20] Se observa una alta tasa de fallos en operaciones ejecutadas en la ventana de 11:08 a 11:38 UTC, donde el mercado presenta una consolidación o reversión que invalida la continuación de la barra ignorada, a diferencia de los trades ganadores que se concentran mayoritariamente en la ventana de 09:48 a 10:58 UTC.

10. [Ciclo #21] Alta tasa de fallos en operaciones ejecutadas en la ventana de 11:08 a 12:23 UTC, donde el mercado presenta una consolidación o reversión que invalida la continuación de la barra ignorada, a diferencia de los trades ganadores que se concentran mayoritariamente en la ventana de 09:48 a 10:58 UTC.

10. [Ciclo #22] Alta tasa de fallos en operaciones ejecutadas en la ventana de 12:23 a 12:38 UTC, donde el mercado muestra una saturación de órdenes y una reversión inmediata tras la barra ignorada, a diferencia de los trades ganadores que evitan esta ventana de alta congestión.

10. [Ciclo #23] Se observa una alta tasa de fallos en operaciones ejecutadas exactamente a las 16:08 UTC, donde una gran cantidad de activos (FIL, WLD, RONIN, VIRTUAL, PEPE, ADA, XRP, ZEC, AAVE) fallan simultáneamente, sugiriendo una trampa de liquidez o una entrada mecánica basada en tiempo que no logra continuación.

10. [Ciclo #24] Se observa una alta tasa de fracaso al operar el mismo activo (específicamente ROBO/USDT) de forma recurrente en un periodo breve tras un fallo inicial, lo que indica una falta de disciplina al intentar recuperar pérdidas en un activo que ya mostró debilidad en la estructura de la barra ignorada.

10. [Ciclo #25] Se observa una correlación crítica entre trades perdedores con una duración inusualmente larga (superando los 300 minutos) y la falta de momentum inmediato. Mientras que los trades ganadores se cierran en un promedio de 50-180 minutos, los perdedores se mantienen en posiciones estancadas durante horas, lo que indica una incapacidad de la estrategia para capitalizar el movimiento y una exposición innecesaria a reversiones.

10. [Ciclo #26] Alta tasa de fallos en operaciones ejecutadas en la ventana de las 04:50 UTC, donde el mercado muestra una falta de continuación de tendencia tras la barra ignorada, resultando en trades de larga duración con P&L negativo.

10. [Ciclo #27] Se observa una alta tasa de fracaso en operaciones con una duración superior a 200 minutos, donde el mercado entra en una fase de estancamiento o reversión lenta, invalidando la premisa de momentum inmediato de la estrategia de barra ignorada.

### andres_valdez
- **Estado**: PLACEHOLDER — pendiente de configuración por el usuario
- **Motor**: custom_rules (reglas configurables via BD)

## Reglas de Mejora Acumuladas

### oliver_elephant

### oliver_sma

### oliver_ignored

### andres_valdez

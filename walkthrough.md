# Rehidratación Persistente de Alertas

El sistema de alertas ahora funciona de manera tolerante a fallos y reinicios. Cuando el bot se cae o es reiniciado externamente, ya no olvida las anomalías que estaban esperando a ser cerradas.

### ¿Qué ha cambiado?
1. **Recuperación Dinámica (`app.py` y `processors.py`)**: 
   Cada vez que el bot se enciende, lee automáticamente la base de datos usando `db.obtener_alertas_pendientes()`. Averigua cuáles fueron las alertas truncadas y recalcula matemática y exáctamente cuánto tiempo le sobraba a cada cronómetro usando la configuración en caché.
   - Si sobraba tiempo, resucita el timer por los minutos remanentes.
   - Si el tiempo de espera ya había terminado mientras el bot estaba caído, emite la alerta retrasada inmediatamente.

2. **Estados Escalados en la Base de Datos (`db.py`)**:
   Implementamos el estado definitivo `2` para tu columna de alerta:
   - `0`: Alerta sin enviar
   - `1`: Anomalía alertada y en espera de volver a normalidad.
   - `2`: Normalización confirmada, avisada y la incidencia está 100% cerrada.
   


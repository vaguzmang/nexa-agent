# NEXA — Evidencia correctiva S2: 10 ejecuciones E2E

Esta evidencia complementa `REPORTE_TECNICO_S2.md` sin reescribir ni ocultar las sesiones históricas allí documentadas.

## Alcance

Cada ejecución procesa una interacción educativa completa:

`actividad + respuesta → diag.v1.1 → agente S2 → tool calling → respuesta → persistencia SQLite → verificación de estado`.

Se ejecuta sobre el código actual de `main`, preservando el contrato de las tres herramientas S2:

1. `get_learning_state`
2. `list_teaching_strategies`
3. `record_learning_event`

## Resultado

- Run ID: `s2-e2e10-final`
- Objetivo: **10 E2E**
- Intentadas: **10**
- Completadas: **10**
- Persistencia verificada: **10**
- Fallidas: **0**
- Llamadas LLM: **41**
- Tool calls observadas: **30**
- Tokens promedio: **18410.9**
- Latencia promedio ms: **58644.3**

Checks:

```text
ten_e2e_attempted: True
ten_e2e_completed: True
ten_e2e_persisted: True
```

## Detalle por ejecución

| Caso | Estado | Persistencia | LLM calls | Tool calls | Tools observadas |
|---|---|---:|---:|---:|---|
| S2-E2E-01 | completed | sí | 4 | 3 | get_learning_state, list_teaching_strategies, record_learning_event |
| S2-E2E-02 | completed | sí | 4 | 3 | get_learning_state, list_teaching_strategies, record_learning_event |
| S2-E2E-03 | completed | sí | 4 | 3 | get_learning_state, list_teaching_strategies, record_learning_event |
| S2-E2E-04 | completed | sí | 4 | 3 | get_learning_state, list_teaching_strategies, record_learning_event |
| S2-E2E-05 | completed | sí | 4 | 3 | get_learning_state, list_teaching_strategies, record_learning_event |
| S2-E2E-06 | completed | sí | 4 | 3 | get_learning_state, list_teaching_strategies, record_learning_event |
| S2-E2E-07 | completed | sí | 4 | 3 | get_learning_state, list_teaching_strategies, record_learning_event |
| S2-E2E-08 | completed | sí | 4 | 3 | get_learning_state, list_teaching_strategies, record_learning_event |
| S2-E2E-09 | completed | sí | 4 | 3 | get_learning_state, list_teaching_strategies, record_learning_event |
| S2-E2E-10 | completed | sí | 5 | 3 | get_learning_state, list_teaching_strategies, record_learning_event |

## Integridad metodológica

- Los casos son ejercicios educativos sintéticos y estables; no son datos personales de estudiantes reales.
- La corrida usa la pasarela configurada en `.env` y no simula respuestas del modelo.
- La base de esta evidencia es independiente de la base normal de NEXA.
- Un fallo permanece registrado como fallo; no se convierte en éxito por edición manual.
- Esta corrección añade evidencia reproducible. No cambia la arquitectura ni aumenta el número de tools de S2.

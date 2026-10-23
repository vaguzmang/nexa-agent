# Reporte técnico NEXA — S2

**Etapa:** S2 — herramientas reales, memoria persistente y tool calling nativo  
**Modelo:** `grok-4.6`  
**Persistencia:** SQLite  
**Rama de desarrollo:** `feature/s2-learning-tools`  
**Commit S2:** `33574ea` — `feat: add S2 native learning tools and persistent memory`

## 1. Objetivo

S2 evoluciona NEXA desde un diagnóstico estructurado hacia un agente académico con memoria persistente y capacidades reales de lectura, consulta pedagógica y escritura.

La etapa mantiene `diag.v1.1` intacto y añade exactamente tres herramientas diferenciadas.

NEXA sigue siendo un **asistente del aprendizaje**. No sustituye al profesor ni presenta objetivos o criterios inferidos como si fueran definidos por el docente.

## 2. Tool calling nativo

El gateway oficial del reto fue probado con `grok-4.6`.

Resultado observado:

```json
{
  "finish_reason": "tool_calls",
  "native_tool_calls_supported": true
}
```

Esto permite que Grok decida qué herramienta invocar y con qué argumentos. El orquestador no ejecuta obligatoriamente una secuencia fija de tres herramientas.

## 3. Las tres herramientas

### 3.1 `get_learning_state(student_id)`

Capacidad: **lectura de memoria del estudiante**.

Devuelve, cuando existe:

- historial;
- último objetivo registrado;
- procedencia `teacher | course | inferred`;
- número de intentos;
- gaps recientes;
- estrategias ya usadas;
- evidencia reciente.

Un alumno sin historial devuelve explícitamente:

```json
{
  "has_history": false,
  "attempts_count": 0
}
```

La tool no crea un alumno al consultar.

### 3.2 `list_teaching_strategies(gap, exclude_types)`

Capacidad: **consulta de catálogo pedagógico**.

SQLite contiene nueve tipos iniciales de estrategia. La tool devuelve opciones elegibles y excluidas; no redacta la lección ni selecciona una única estrategia.

La decisión final pertenece a Grok/NEXA.

### 3.3 `record_learning_event(...)`

Capacidad: **escritura real append-only**.

Registra:

- estudiante;
- objetivo y procedencia;
- actividad;
- gap;
- estrategia aplicada;
- estado de la estrategia;
- resultado diagnóstico;
- evidencia breve;
- timestamp;
- `event_id`.

Semántica congelada:

- `diagnostic_outcome` describe la respuesta entrante;
- `strategy_type` es la intervención que se aplica;
- en ese mismo turno, `strategy_result="inconclusive"` significa “resultado aún no observado”;
- `helped`/`failed` requieren evidencia posterior.

## 4. Persistencia

SQLite:

```text
data/nexa.db
```

Tablas:

- `students`
- `teaching_strategies`
- `learning_events`

La base local está excluida de Git; el código de esquema y semillas sí está versionado.

## 5. Pruebas automatizadas

Resultado final antes de entrega:

```text
Ran 50 tests
OK
```

Los tests cubren S1 y S2, incluyendo:

- invariantes de `diag.v1.1`;
- transporte/telemetría;
- ausencia de “respuesta correcta” en la entrada;
- base SQLite y semillas;
- alumno sin historial;
- lectura de historial real;
- escritura con `event_id`;
- rechazo de estrategias desconocidas;
- ausencia de `mastery`;
- tool desconocida;
- límite de rondas;
- tool results reinyectados a Grok;
- semántica de `strategy_result`.

## 6. Ejecución real — sesión 1

Caso: ciclo del agua.

Diagnóstico:

- `evidence.result=partial`
- `gap=incomplete_procedure`
- `next_step=teach`

Grok decidió autónomamente:

1. `get_learning_state`
   - `has_history=false`
   - `attempts_count=0`

2. `list_teaching_strategies`
   - `guided_practice`
   - `hint`
   - `worked_example`

3. Grok eligió `worked_example`.

4. `record_learning_event`
   - `strategy_result=inconclusive`
   - `diagnostic_outcome=partial`
   - `objective_source=inferred`
   - escritura exitosa con `event_id`.

Metadatos observados:

- 3 tool calls;
- 4 llamadas LLM;
- 11,613 tokens totales reportados por las respuestas del gateway;
- 25,676 ms de latencia agregada;
- modelo solicitado/reportado: `grok-4.6`.

## 7. Ejecución real — sesión 2

Mismo `student_id`.

`get_learning_state` devolvió:

```text
has_history=true
attempts_count=1
previous_gaps=[incomplete_procedure]
strategies_tried=[worked_example / inconclusive]
objective_source=inferred
can_cite_as_teacher_objective=false
```

Grok consultó nuevamente el catálogo y eligió `guided_practice`.

La segunda interacción fue registrada con un nuevo `event_id`.

Metadatos:

- 3 tool calls;
- 4 llamadas LLM;
- 12,646 tokens totales reportados;
- 35,908 ms de latencia agregada;
- modelo solicitado/reportado: `grok-4.6`.

La prueba demuestra memoria persistente y una nueva elección pedagógica. No se afirma que `worked_example` haya “fracasado”, porque su resultado seguía `inconclusive`.

## 8. Manejo realista de fallo de herramienta

Se realizó una prueba controlada de escritura con destino SQLite inválido.

Secuencia observada:

1. Estado inicial:
   - `attempts_count=2`.

2. Grok decidió:
   - `record_learning_event`.

3. La tool devolvió:

```json
{
  "ok": false,
  "error_code": "storage_error",
  "message": "No fue posible persistir esta interacción: OperationalError."
}
```

4. NEXA respondió:

> Esta interacción no pudo persistirse, así que el evento no quedó registrado. No hay un `event_id` que confirmar.

5. Verificación posterior:
   - `attempts_before=2`
   - `attempts_after=2`
   - `history_unchanged=true`
   - `event_was_persisted=false`

Esto demuestra que la memoria es un estado real en SQLite y no una afirmación del modelo.

## 9. Guardrails

- No declarar mastery.
- No inventar historial.
- No fingir una escritura.
- No atribuir objetivos inferidos al profesor.
- No presentar criterios inferidos como rúbrica docente.
- No usar `helped/failed` sin evidencia posterior.
- No repetir automáticamente llamadas de almacenamiento tras un fallo.
- Límite de rondas para prevenir loops de tool calling.
- Telemetría sin API key ni prompts completos.

## 10. Limitaciones deliberadas

No se implementa aún:

- filtro por `objective_id` estable;
- tabla curricular de objetivos;
- PostgreSQL;
- embeddings/vector DB;
- multiagente;
- motor formal de mastery;
- optimización agresiva de tokens.

Estas extensiones se posponen para no introducir complejidad prematura antes de validar el núcleo agente.

## 11. Conclusión

S2 demuestra tres capacidades reales y distintas:

**leer memoria → consultar repertorio pedagógico → persistir evidencia**.

Grok controla dinámicamente el uso de herramientas mediante tool calling nativo. SQLite conserva la evidencia entre sesiones y los fallos de persistencia son visibles y honestos.

La etapa transforma NEXA de un diagnóstico estructurado en un primer agente académico con memoria y adaptación.

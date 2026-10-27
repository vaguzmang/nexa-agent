# NEXA — REPORTE TÉCNICO S3

## 1. Objetivo

S3 valida NEXA con ejecuciones end-to-end, una evaluación propia reproducible y medición de costo por tarea.

## 2. Naturaleza y cobertura de los datos

- Escenarios objetivo del set controlado: **50**.
- Ejecuciones end-to-end completadas y registradas: **49**.
- Escenarios con fallo técnico persistente sin `task_run`: **1**.
- Intentos técnicos fallidos registrados para esos escenarios: **2**.
- Ejecuciones optimizadas de desarrollo no marcadas y excluidas: **5**.
- Los casos son **ejecuciones reales del agente contra el modelo/gateway**, diseñadas de forma controlada.
- No se presentan como una cohorte natural ni como datos personales de estudiantes reales.
- Los bancos sintéticos previos se usan solo para diseño adversarial y no se contabilizan como datos reales de S3.

## 3. Evaluación propia

La evaluación contract-based revisa por caso la clasificación del turno, necesidad de diagnóstico, resultado/gap cuando aplica, continuidad de objetivo/episodio, señales de retrieval/transfer, ausencia de pseudo-tool-calls, ausencia de mastery no sustentado y ejecución sin errores.

- Quality pass entre ejecuciones completas: **46/49 (93.88%)**.
- Completitud técnica del set: **49/50 (98.0%)**.
- Éxito integral del set (quality pass / todos los escenarios objetivo): **46/50 (92.0%)**.
- Quality fails conservados en el benchmark: **3**.
- Repairs acumulados en ejecuciones completas: **0**.

### Casos que no pasaron la evaluación

- **S3-R13** (learning_request): quality fail.
  - esperado: `{"should_diagnose": false, "task_type": "procedural", "forbid_mastery": true}`
  - observado: `{"turn_type": "learning_request", "should_diagnose": false, "evidence_result": "insufficient_evidence", "gap_type": "none", "task_type": "conceptual", "response_format": "open", "retrieval_required": false, "transfer_context": false, "objective_action": "create_inferred", "episode_action": "start_episode", "selected_strategy": "concept_explanation", "errors": 0, "repairs": 0}`
- **S3-R27** (diagnosis_required): quality fail.
  - esperado: `{"should_diagnose": true, "evidence_result": "meets", "gap_type": "none", "forbid_mastery": true}`
  - observado: `{"turn_type": "attempt", "should_diagnose": true, "evidence_result": "partial", "gap_type": "incomplete_procedure", "task_type": "mixed", "response_format": "open", "retrieval_required": false, "transfer_context": false, "objective_action": "create_inferred", "episode_action": "start_episode", "selected_strategy": "worked_example", "errors": 0, "repairs": 0}`
- **S3-R45** (other): quality fail.
  - esperado: `{"should_diagnose": true, "forbid_mastery": true}`
  - observado: `{"turn_type": "metacognitive", "should_diagnose": false, "evidence_result": "insufficient_evidence", "gap_type": "none", "task_type": "conceptual", "response_format": "open", "retrieval_required": false, "transfer_context": false, "objective_action": "create_inferred", "episode_action": "start_episode", "selected_strategy": "probe", "errors": 0, "repairs": 0}`

### Fallos técnicos persistentes

- **S3-R44**: 2 intento(s) técnico(s) fallido(s).
  - `DiagnosisGenerationError`: Grok no produjo un DiagnosisResult válido después del único intento de reparación.
  - `DiagnosisGenerationError`: Grok no produjo un DiagnosisResult válido después del único intento de reparación.

## 4. Costo y rendimiento por tarea completada

- Tokens reportados promedio: **7454.27**
- Mediana: **6667**
- p95: **11154.4**
- Tokens visibles promedio: **5564.43**
- Latencia promedio: **32898.02 ms**
- LLM calls promedio: **3.24**
- Tool calls promedio: **1.88**
- Costo USD estimado promedio: **0.02**
- Costo USD estimado mediana: **0.02**
- Costo USD estimado p95: **0.04**

El costo USD se calcula con las tarifas configuradas. Para la estimación de referencia de esta evaluación se usaron US$2/M input y US$6/M output; los reasoning tokens se tratan como output facturable. Esta estimación no equivale ni pretende reconstruir los créditos internos del gateway del reto.

## 5. Comparación con baseline

- Baseline tokens promedio: **13771.25**
- Reducción de tokens reportados: **45.87%**
- Reducción de tokens visibles: **38.82%**
- Reducción observada de latencia: **50.17%**
- Reducción de tool calls: **24.8%**

## 6. Resultados por flujo

### diagnosis_required
- tareas completadas: 16
- tokens avg / median / p95: 10027.56 / 9635.5 / 11754.25
- latencia promedio: 49050.94 ms
- quality success rate: 0.9375
- costo USD promedio: 0.03

### help_request
- tareas completadas: 7
- tokens avg / median / p95: 6853.86 / 6413 / 8391.0
- latencia promedio: 28459.29 ms
- quality success rate: 1.0
- costo USD promedio: 0.02

### independent_correct
- tareas completadas: 1
- tokens avg / median / p95: 9148.0 / 9148 / 9148
- latencia promedio: 37455.0 ms
- quality success rate: 1.0
- costo USD promedio: 0.03

### learning_request
- tareas completadas: 14
- tokens avg / median / p95: 6447.5 / 6485.5 / 6756.8
- latencia promedio: 25689.29 ms
- quality success rate: 0.9286
- costo USD promedio: 0.02

### objective_switch
- tareas completadas: 3
- tokens avg / median / p95: 6267.67 / 6319 / 6453.1
- latencia promedio: 21385.67 ms
- quality success rate: 1.0
- costo USD promedio: 0.02

### other
- tareas completadas: 5
- tokens avg / median / p95: 6660.2 / 6667 / 6869.6
- latencia promedio: 27974.6 ms
- quality success rate: 0.8
- costo USD promedio: 0.02

### resume_reassessment
- tareas completadas: 3
- tokens avg / median / p95: 1774.67 / 1660 / 1975.9
- latencia promedio: 8946.0 ms
- quality success rate: 1.0
- costo USD promedio: 0.01

## 7. Controles metodológicos

- Un fallo de calidad del agente **no se elimina** del benchmark: permanece como caso válido con `quality_pass=false`.
- Un fallo técnico que impide producir `task_run` se conserva en `artifacts/S3_BATCH_FAILURES.jsonl` y se contabiliza en la cobertura integral del set.
- Solo se excluyen pruebas de desarrollo/montaje explícitamente fuera del benchmark.
- `meets` no se interpreta como mastery.
- Una interrupción por cambio de tema no se registra como fracaso de estrategia.
- La analítica poblacional no interviene en el ranking pedagógico individual.

## 8. Limitaciones

- El benchmark controlado no sustituye una validación longitudinal con una cohorte natural de estudiantes.
- La latencia depende también del gateway y del proveedor.
- El costo USD de referencia usa tarifas configuradas; los créditos internos del reto pueden seguir otra regla.
- El escenario técnico fallido se reporta como limitación reproducible y no se oculta del resultado integral.

## 9. Evidencias reproducibles

- `python -m unittest discover -s tests -v`
- `python s3_eval_report.py`
- `python s3_eval_export.py`
- `python s3_build_report.py`
- `artifacts/S3_BATCH_FAILURES.jsonl`

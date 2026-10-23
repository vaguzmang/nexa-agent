# Informe técnico de NEXA S1 v1.1

**Fecha:** 22 de octubre de 2026  
**Versión documentada:** `4bd54f6fcea7289ee641ccf45a6950a3e1ecd913`  
**Estado técnico:** S1 v1.1 publicada en `main`; 28/28 pruebas locales satisfactorias y una ejecución real con Grok verificada. La aprobación formal del panel y la carga del video son pasos separados.

## 1. Propósito

NEXA es un agente de apoyo al aprendizaje. Acompaña al estudiante mediante diagnóstico, explicación, práctica, evaluación y seguimiento, sin sustituir al profesor ni atribuirse decisiones pedagógicas que pertenecen al docente.

S1 v1.1 establece una base auditable: recibe una actividad o pregunta y la respuesta del estudiante, obtiene un diagnóstico estructurado mediante Grok, valida el resultado con Pydantic y registra metadatos seguros de transporte y consumo. La interfaz ya no solicita al alumno una “respuesta correcta”.

## 2. Principio pedagógico

**NEXA es un ayudador del aprendizaje, no el profesor y no pretende sustituirlo al 100%.**

- Una rúbrica, objetivo, actividad o criterio definido por el docente o curso tiene prioridad y debe conservar su procedencia.
- NEXA puede crear criterios internos de diagnóstico en aprendizaje libre, pero deben identificarse como inferidos por la IA; nunca se presentan como “rúbrica del profesor”.
- La evolución de S2 deberá distinguir la procedencia del contexto, como mínimo: `teacher`, `course` e `inferred`.
- El diagnóstico S1 no escribe mastery. `MASTERED`, `RETRY` y `ESCALATE` quedan reservados para una etapa posterior de evaluación y actualización de progreso.

## 3. Flujo técnico S1 v1.1

1. La CLI recibe la actividad o pregunta y la respuesta del estudiante.
2. `prompt.py` construye la instrucción pedagógica y exige el contrato `diag.v1.1`.
3. `grok_client.py` envía la solicitud al gateway del reto con el modelo configurado.
4. La respuesta se valida con `DiagnosisResult.model_validate_json()`.
5. Si existe contenido pero falla JSON/schema —o llega truncado por `length`— se permite exactamente un repair lógico. No existe una tercera llamada.
6. La CLI presenta el diagnóstico validado y metadatos técnicos seguros.

## 4. Contrato `diag.v1.1`

El diagnóstico contiene:

- `objective`: dominio y habilidad evaluada.
- `evidence`: tipo de evidencia, resultado, resumen y criterios cuando aplica.
- `understanding`: comprensión demostrada y faltante.
- `gap`: brecha de aprendizaje identificada.
- `next_step`: `ask_clarifying`, `teach`, `practice` o `escalate`.

El contrato quedó congelado después de cerrar los casos de rúbrica con evidencia insuficiente, reducción de criterios parciales y restricciones para gaps `uncertain`.

## 5. Transporte y observabilidad

- Timeout explícito.
- `max_retries=0`.
- Los errores de autenticación, rate limit, timeout y conexión no activan el repair de JSON.
- `finish_reason` participa en el control de flujo: `length` se considera truncamiento; `content_filter` es terminal.
- Metadatos por intento: modelo solicitado/reportado, `finish_reason`, tokens cuando existen, latencia, outcome, clase de error, HTTP status y truncamiento.
- Metadatos agregados por operación: `success`, `repaired`, `transport_error` o `invalid_output`.
- La telemetría no persiste por defecto el texto completo del estudiante.

## 6. Pruebas automatizadas

**Resultado local: 28/28 pruebas satisfactorias.**

Las pruebas cubren, entre otros casos:

- invariantes de `diag.v1.1`;
- rúbricas y `insufficient_evidence`;
- separación entre `meets` y dominio final;
- gaps `uncertain`;
- timeout, autenticación y rate limit sin repair;
- único repair y ausencia de una tercera llamada;
- truncamiento;
- modelo, `finish_reason`, usage y latencia;
- ausencia de usage como `None`, nunca cero inventado;
- ausencia del campo “respuesta correcta” en la experiencia del alumno.

## 7. Ejecución real con Grok

Se ejecutó un caso sintético de Ciencias Naturales posterior a la rotación de la credencial.

- Pregunta: “porque llueve”.
- Respuesta del estudiante: “porque evaporizacion y precipitacion del agua”.
- Resultado diagnóstico: `partial`.
- Gap: `incomplete_procedure`.
- Siguiente paso: `teach`.
- Transporte: `success`.
- Llamadas: 1 (`primary`), sin repair.
- Modelo solicitado: `grok-4.6`.
- Modelo reportado: `grok-4.6`.
- `finish_reason`: `stop`.
- `prompt_tokens`: 1860.
- `completion_tokens`: 285.
- `total_tokens` reportado por el gateway: 3800.
- Latencia: 27,846 ms.
- `truncated`: false.

**Nota:** el `total_tokens` reportado por el gateway no coincide aritméticamente con `prompt_tokens + completion_tokens`. Se preservan los valores tal como fueron reportados; NEXA no corrige ni inventa métricas del proveedor.

## 8. Seguridad y privacidad

- La clave del reto permanece en `.env` local.
- `.env` está ignorado por Git.
- `.env.example` contiene solo valores de ejemplo.
- La telemetría no necesita persistir el prompt ni la completion completa.
- No se muestran secretos ni headers de autorización en la demo.
- Los casos de demostración utilizan datos sintéticos.

## 9. Límites de S1 y evolución a S2

S1 v1.1 diagnostica evidencia de aprendizaje. El ciclo educativo completo pertenece a S2, incluyendo:

1. `get_learning_context()` — objetivo, actividad, historial, contexto docente/curso y procedencia.
2. `retrieve_teaching_strategy()` — explicación, analogía, ejemplo o práctica adaptada.
3. `assess_and_update_mastery()` — nueva evidencia y resultado `MASTERED`, `RETRY` o `ESCALATE`.

S2 también deberá diferenciar explícitamente una rúbrica oficial del docente de criterios internos inferidos por NEXA.

## 10. Estado de cierre

| Elemento | Estado |
|---|---|
| Código S1 v1.1 | Cerrado y publicado en `main` |
| Pruebas automatizadas | 28/28 OK |
| Ejecución real Grok | Verificada |
| Informe técnico | Listo |
| Video S1 | Pendiente de grabación/carga |
| Estado `APPROVED` del panel | Pendiente de confirmar |

## Referencia técnica

Repositorio: `github.com/vaguzmang/nexa-agent`  
Commit: `4bd54f6fcea7289ee641ccf45a6950a3e1ecd913` — `feat: finalize S1 v1.1 structured diagnosis and telemetry`

> La aprobación formal de S1 depende del panel/organización del reto y no se infiere únicamente del funcionamiento técnico.

# NEXA — REPORTE TÉCNICO S3 V2

## 1. Motivo de la actualización

Esta versión responde directamente a la retroalimentación del hito S3:
1. utilizar datos reales del dominio;
2. comparar el costo estimado con el costo real observado en la pasarela;
3. mantener visibles los fallos y separar problemas del agente de problemas de preparación de datos.

## 2. Datos reales del dominio

Se utilizó un set de 30 escenarios construido a partir de preguntas oficiales liberadas de Saber 11 por el Icfes:
- Matemáticas;
- Ciencias Naturales.

Las preguntas se descargaron desde las fuentes oficiales. El repositorio conserva manifiestos y referencias auditables; los cuadernillos completos no se republican.

## 3. Primera corrida real-domain

- Escenarios objetivo: **30**
- Ejecuciones completas: **29**
- Quality pass: **26**
- Fallos de calidad aparentes: **3**
- Fallos técnicos: **1**

### Auditoría posterior de calidad de entrada

Los casos ICFES-07, ICFES-12 e ICFES-13 fueron reclasificados como problemas de preparación de entrada:
- pérdida de fracciones durante extracción PDF;
- separación de datos estructurados;
- pérdida de una tabla necesaria para responder.

Estos casos no se borraron. Permanecen documentados como fallos del pipeline de preparación.

## 4. Remediación controlada

Se ejecutaron tres reemplazos oficiales ICFES con contexto textual suficiente:

- `ICFES-V2-R12`: PASS
- `ICFES-V2-R13`: PASS
- `ICFES-V2-R07`: ERROR técnico

Además se ejecutó un único retry controlado de `ICFES-29`:
- primera pasada: ERROR técnico;
- único retry: PASS.

Resultado validado después de la remediación:
- escenarios objetivo: **30**
- escenarios validados con PASS: **29**
- escenario técnico no resuelto: **1**
- éxito integral final por escenario: **96.67%**

La primera falla técnica de ICFES-29 permanece registrada y no fue eliminada.

## 5. Costo real del gateway — corrida inicial

Panel antes:
- requests: **254**
- input tokens: **489,013**
- output tokens: **56,032**
- costo: **USD 2.32**

Panel después:
- requests: **406**
- input tokens: **901,051**
- output tokens: **70,780**
- costo: **USD 3.91**

Incremento:
- requests: **152**
- input tokens: **412,038**
- output tokens: **14,748**
- costo real: **USD 1.59**
- costo real por escenario objetivo: **USD 0.053**

## 6. Costo real de la remediación

Antes:
- requests: **406**
- costo: **USD 3.91**

Después:
- requests: **423**
- costo: **USD 4.08**

Incremento:
- requests: **17**
- input tokens: **44,488**
- output tokens: **1,598**
- costo: **USD 0.17**
- costo por intento de remediación: **USD 0.0425**
- costo por ejecución completada: **USD 0.056667**

## 7. Costo total para llegar al resultado final S3 V2

Desde el snapshot inicial hasta finalizar la remediación:
- requests incrementales: **169**
- input tokens incrementales: **456,526**
- output tokens incrementales: **16,346**
- costo real total incremental: **USD 1.76**

Costo real total invertido por escenario final objetivo:
- **USD 0.058667 / escenario**

Esta cifra incluye tanto la corrida inicial como las ejecuciones adicionales necesarias para auditar y remediar el set.

## 8. Comparación con la estimación anterior

S3 V1 reportó aproximadamente **USD 0.02 por tarea** usando tarifas configuradas por tokens.

La medición real del gateway para el benchmark ICFES fue aproximadamente:
- **USD 0.053 por escenario** en la corrida inicial;
- **USD 0.0587 por escenario final** si se incluye la remediación.

Por tanto, el costo observado real del gateway es la métrica principal para la toma de decisiones operativas. La estimación por tokens se conserva solo como referencia secundaria.

## 9. Integridad metodológica

- Los fallos no se eliminaron.
- Los problemas de extracción se separaron de los fallos del agente.
- No se modificó NEXA para hacer pasar retrospectivamente el benchmark.
- Se permitió un único retry controlado del fallo técnico ICFES-29.
- El fallo técnico de `ICFES-V2-R07` permanece no resuelto.
- Las fuentes reales del dominio son oficiales y auditables.

## 10. Conclusión

S3 V2 corrige los tres puntos señalados por el equipo evaluador:
- datos reales del dominio;
- evaluación propia con fallos visibles;
- costo real por tarea medido con la bitácora/panel de la pasarela.

S3 queda listo como base para S4, donde la prioridad pasa de calidad/costo a operación desatendida y volumen.

# NEXA — REPORTE TÉCNICO S4

## 1. Objetivo

S4 valida operación real de NEXA a volumen, de forma desatendida y usando la llave oficial del reto.

Requisitos evaluados:
- 1.000+ unidades de trabajo completas.
- 12+ horas seguidas de operación desatendida.
- consumo real verificable en la pasarela.
- recuperación automática frente a errores transitorios.

## 2. Unidad de trabajo

Una unidad es una interacción educativa completa procesada end-to-end por NEXA:

entrada → intake → diagnóstico cuando aplica → decisión pedagógica → herramientas → respuesta → persistencia.

Las llamadas individuales a Grok y los tool calls internos no se contabilizan como unidades.

## 3. Configuración oficial

- Run ID: `s4-official-20261106`
- Workload: **1.300 unidades**
- Target mínimo: **1.100 completadas**
- Workers: **3**
- Heartbeat aproximado: cada 60 segundos
- Persistencia: SQLite

Distribución:
- 260 intentos evaluables
- 650 solicitudes de explicación
- 390 solicitudes de pista

## 4. Resultado

- Estado: **completed**
- Inicio UTC: **2026-11-06T21:38:56.414302+00:00**
- Fin UTC: **2026-11-07T09:55:53.952749+00:00**
- Duración: **12.283 horas**
- Completadas: **1.256**
- Target: **1.100**
- Cumplimiento del target: **114.18%**
- Dead letters: **2**
- Pendientes al cierre: **42**

Checks:
- `completed>=1000: True`
- `elapsed>=12h: True`
- `heartbeat_gap<=180s: True`

## 5. Operación desatendida

- Heartbeats: **736**
- Gap máximo: **60.25 s**
- Unidades con retry: **20**
- Tokens promedio/unidad: **14.971,3**
- Latencia promedio: **55.314,81 ms**
- LLM calls promedio: **4,05**
- Ritmo promedio: **102.26 unidades/hora**

La corrida superó las 12 horas por aproximadamente **16.98 minutos**.

## 6. Recuperación automática

El runner:
- movió fallos transitorios a `retry_wait`;
- reintentó automáticamente;
- mantuvo el resto de la cola activa;
- aisló fallos no recuperables en `dead_letter`;
- continuó sin intervención manual.

Se registraron **20 unidades con retry** y **2 dead letters**.

## 7. Costo real del gateway

BEFORE:
- 1.373 requests
- 3.715.066 input tokens
- 159.605 output tokens
- USD 12.90

AFTER:
- 6.580 requests
- 18.733.172 input tokens
- 650.108 output tokens
- USD 60.96

Incremento atribuible a la corrida oficial:
- **5.207 requests**
- **15.018.106 input tokens**
- **490.503 output tokens**
- **USD 48.06**

Costo real por unidad completada:
- **USD 0.038264**

Peticiones promedio por unidad:
- **4.1457**

## 8. Integridad

Se mantienen visibles:
- retries;
- dead letters;
- unidades pendientes;
- heartbeats;
- costo real.

No se eliminaron fallos para mejorar artificialmente el resultado.

## 9. Conclusión

NEXA cumplió los dos requisitos centrales de S4:

1. **1.256 unidades completas**, por encima de 1.000.
2. **12.283 horas desatendidas**, por encima de 12 horas.

Además demostró continuidad con 736 heartbeats, recuperación automática y consumo verificable en la pasarela real.

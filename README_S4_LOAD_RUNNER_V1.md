# NEXA S4 — Load Runner V1

Objetivo: demostrar **1,000+ unidades completas** y **12+ horas desatendidas** usando la llave real del reto.

## Unidad de trabajo
Una unidad es una interacción educativa completa procesada por `run_student_turn`:
entrada → intake → diagnóstico si aplica → decisión → tools → respuesta → persistencia.

Las llamadas a Grok y los tool calls **NO** cuentan como unidades.

## Workload
`python s4_prepare_workload.py --units 1300`

Genera 1,300 interacciones distintas sobre preguntas reales ICFES ya preparadas:
- 20% respuestas evaluables;
- 50% solicitudes de explicación;
- 30% solicitudes de pista.

Cada unidad tiene `unit_id` y `student_id` propios. Se excluyen del generador los casos cuyo contexto quedó mutilado en la extracción y el caso técnico que aún está bajo auditoría.

## Corrida oficial propuesta
- 3 workers;
- 105 lanzamientos/hora;
- 12.25 horas mínimas;
- target: 1,100 completadas;
- máximo 3 intentos con backoff 15s / 60s / 180s;
- heartbeat cada 60s;
- SQLite de carga separado: `data/s4_load.db`.

El runner **no finaliza** solo por llegar a 1,100 si todavía no han transcurrido 12.25 horas. Si pasan 12.25 horas sin alcanzar el target, continúa automáticamente hasta alcanzarlo.

## Preparación
```powershell
python s4_prepare_workload.py --units 1300
python s4_load_runner.py --run-id s4-dry --dry-run
```

## Ensayos previos obligatorios
1. 20 unidades.
2. 100 unidades.
3. 1 hora desatendida.
4. Solo después: corrida oficial de 12+ horas.

## Corrida oficial
```powershell
.\s4_start_12h.ps1
```

## Evidencia
```powershell
python s4_report.py --run-id <RUN_ID>
python s4_gateway_cost.py snapshot --label before ...
python s4_gateway_cost.py snapshot --label after ...
python s4_gateway_cost.py report --completed <COMPLETED>
```

El reporte verifica explícitamente:
- `completed >= 1000`;
- `elapsed >= 12h`;
- continuidad de heartbeats;
- retries y dead letters;
- tokens, latencia y llamadas promedio.

## Antes de la corrida oficial
- conectar el equipo a corriente;
- desactivar suspensión automática;
- confirmar red estable;
- cerrar actualizaciones/reinicios programados;
- registrar captura BEFORE del panel del gateway;
- no operar ni reiniciar manualmente durante la corrida.

## Preflight y supervisor
```powershell
.\s4_preflight.ps1
.\s4_supervisor_12h.ps1
```

Para la corrida oficial se recomienda el supervisor: cualquier relanzamiento es automático, conserva el mismo `run_id` y recupera el checkpoint; no requiere intervención manual.


## Validación escalonada V2

### 1. Preflight
```powershell
.\s4_preflight.ps1
```

### 2. Dry-run
```powershell
python s4_prepare_workload.py --units 1300
python s4_load_runner.py --run-id s4-dry-v2 --db data\s4_dry_v2.db --dry-run
```

### 3. Prueba 20
```powershell
.\s4_test_20.ps1
```

### 4. Prueba 100
```powershell
.\s4_test_100.ps1
```

### 5. Prueba 1 hora
```powershell
.\s4_test_1h.ps1
```

### 6. Oficial
Solo después de aprobar las etapas anteriores:
```powershell
.\s4_official_12h.ps1
```

Cada etapa usa una base SQLite independiente para no mezclar evidencia.

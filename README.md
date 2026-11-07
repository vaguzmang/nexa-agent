# NEXA Agent

NEXA es un agente educativo orientado a evaluar evidencia de aprendizaje del turno, detectar brechas observables y proponer intervenciones pedagógicas prudentes.

## Semana 1 — diagnóstico estructurado

S1 demuestra un flujo end-to-end de diagnóstico con contrato `diag.v1.1`.

### Entrada actual

El usuario proporciona únicamente:

- una actividad o pregunta;
- la respuesta del estudiante.

NEXA **no recibe una “respuesta correcta” como campo de entrada**.

Para conocimiento general estable, el modelo puede inferir un referente educativo mínimo. Si la actividad depende de una fuente, rúbrica, texto previo, convención local o información no proporcionada, NEXA debe declarar evidencia insuficiente en lugar de inventar el referente.

### Flujo

1. El usuario ingresa la actividad o pregunta.
2. El usuario ingresa la respuesta del estudiante.
3. NEXA envía esa evidencia a Grok.
4. La salida se valida con Pydantic contra `diag.v1.1`.
5. Si la primera salida no cumple el contrato lógico o estructural, existe como máximo **un intento de reparación**.
6. NEXA entrega el diagnóstico estructurado y telemetría técnica segura.

El cliente de diagnóstico no aplica retries HTTP automáticos (`max_retries=0`).

### Contrato de diagnóstico

La salida modela, entre otros elementos:

- `objective`: dominio y habilidad evaluada;
- `evidence`: tipo, resultado y resumen de la evidencia;
- `understanding`: qué se demostró y qué falta;
- `gap`: presencia, tipo y descripción de la brecha;
- `next_step`: siguiente acción educativa.

Resultados de evidencia posibles:

- `meets`
- `partial`
- `does_not_meet`
- `insufficient_evidence`

`meets` describe el artefacto de este turno. **No equivale a mastery o dominio global del estudiante.**

### Ejecución

```powershell
python main.py
```

Ejemplo de entrada:

```text
Actividad o pregunta a evaluar: ¿Cuánto es 12 x 8?
Respuesta del estudiante: 84
```

La salida es un objeto JSON validado por `schemas/diagnosis.py`.

## Evolución del proyecto

- `REPORTE_TECNICO_S1.md`: diagnóstico estructurado y transporte seguro.
- `REPORTE_TECNICO_S2.md`: tres herramientas reales y memoria persistente.
- `REPORTE_TECNICO_S3_V2.md`: evaluación real-domain con material oficial ICFES y costo real.
- `REPORTE_TECNICO_S4.md`: carga desatendida de más de 12 horas.

NEXA se mantiene como **agente educativo**. LMS, analítica, recursos y sistemas humanos son integraciones externas y no sustituyen al agente.

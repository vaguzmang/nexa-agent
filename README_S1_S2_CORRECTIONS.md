# Correcciones mínimas S1 / S2

## S1

Se alinea `README.md` con la implementación vigente:

- entrada = actividad/pregunta + respuesta del estudiante;
- no existe campo de “respuesta correcta”;
- contrato `diag.v1.1`;
- un único intento lógico de reparación;
- sin retries HTTP automáticos;
- `meets` no equivale a mastery.

No se cambia la arquitectura S1.

## S2

Se añade `s2_e2e_10.py` para producir la evidencia faltante de la rúbrica:

- exactamente 10 ejecuciones educativas E2E;
- llamadas reales a la pasarela configurada;
- uso del agente y sus herramientas existentes;
- SQLite independiente para la corrida;
- verificación posterior de persistencia;
- JSONL, resumen JSON y reporte Markdown reproducibles.

No se agregan herramientas y no se modifica la semántica de almacenamiento del agente.

### Ejecución

```powershell
python s2_e2e_10.py --run-id s2-e2e10-final
```

Al finalizar debe aparecer:

```text
S2_E2E_10_OK=True
```

La evidencia generada queda en:

- `artifacts/S2_E2E_10_RESULTS.jsonl`
- `artifacts/S2_E2E_10_SUMMARY.json`
- `REPORTE_TECNICO_S2_E2E_10.md`

La base de datos usada para la corrida queda bajo `data/` y debe conservarse como respaldo local, no necesariamente versionarse.

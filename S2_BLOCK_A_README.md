# NEXA S2 — Bloque A: memoria y herramientas

Este bloque añade exactamente tres herramientas reales:

1. `get_learning_state()` — consulta memoria persistente del alumno.
2. `list_teaching_strategies()` — consulta catálogo pedagógico y devuelve opciones.
3. `record_learning_event()` — escribe un evento real append-only.

Persistencia: SQLite (`data/nexa.db`), sin servidor.

## Principios

- NEXA no sustituye al profesor.
- `objective_source` conserva procedencia: `teacher | course | inferred`.
- Solo `teacher` autoriza `can_cite_as_teacher_objective=true`.
- No existe campo `mastery`.
- El GET no crea alumnos.
- El catálogo no redacta la lección ni decide la estrategia final.
- Un evento solo se considera guardado si la tool devuelve `event_id`.
- Los errores se devuelven como objetos controlados; no se exponen stack traces al modelo.

## Inicializar

```powershell
python -m s2.setup
```

## Tests

```powershell
python -m unittest discover -s tests -v
```

La integración con tool-calling de Grok se realiza en el Bloque B, después de validar estas tres tools.

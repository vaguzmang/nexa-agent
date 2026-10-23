# NEXA S2 — Bloque B: orquestación nativa con Grok

Añade:

- `s2/agent.py`: loop de tool-calling nativo.
- `s2_demo.py`: demo CLI S1 -> S2.
- `tests/test_s2_agent.py`: tests del orquestador.

No modifica `diag.v1.1` ni las tres tools de Bloque A.

## Flujo

1. S1 genera diagnóstico validado.
2. S2 envía diagnóstico/contexto a Grok con las tres tool definitions.
3. Grok decide si invoca tools.
4. NEXA ejecuta la tool real y devuelve su resultado a Grok.
5. Grok puede encadenar nuevas tools.
6. Grok produce respuesta final al estudiante.
7. La CLI imprime traza de tools y metadatos.

## Pruebas

```powershell
python -m unittest discover -s tests -v
```

## Demo real

```powershell
python s2_demo.py
```

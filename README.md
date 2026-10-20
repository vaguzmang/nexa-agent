# NEXA Agent

NEXA es un agente educativo orientado a detectar dificultades de aprendizaje a partir de las respuestas de los estudiantes y proponer intervenciones pedagógicas.

## Semana 1 - Agent Challenge

El objetivo de esta primera versión es demostrar un flujo end-to-end funcional.

### Flujo actual

1. El usuario ingresa:
   - una pregunta
   - la respuesta correcta
   - la respuesta del estudiante

2. NEXA envía la información a Grok mediante la API proporcionada por el Agent Challenge.

3. Grok analiza la respuesta.

4. NEXA entrega una salida estructurada con:
   - si la respuesta es correcta
   - tipo de error
   - diagnóstico
   - intervención educativa
   - siguiente paso

## Ejemplo

Pregunta:

¿Cuánto es 12 x 8?

Respuesta correcta:

96

Respuesta del estudiante:

84

Salida esperada:

```json
{
  "correcta": false,
  "tipo_error": "error de cálculo",
  "diagnostico": "...",
  "intervencion": "...",
  "siguiente_paso": "..."
}
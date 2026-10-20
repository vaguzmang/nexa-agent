def crear_prompt(pregunta, respuesta_correcta, respuesta_estudiante):
    return f"""
Analiza la respuesta de un estudiante.

Pregunta:
{pregunta}

Respuesta correcta:
{respuesta_correcta}

Respuesta del estudiante:
{respuesta_estudiante}

Tu tarea es detectar el posible tipo de error y proponer una intervención educativa corta.

Devuelve exclusivamente un JSON válido con esta estructura:

{{
  "correcta": true,
  "tipo_error": "",
  "diagnostico": "",
  "intervencion": "",
  "siguiente_paso": ""
}}
"""

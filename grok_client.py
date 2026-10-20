import os
from dotenv import load_dotenv
from openai import OpenAI

from prompt import crear_prompt

load_dotenv()

client = OpenAI(
    api_key=os.getenv("GROK_API_KEY"),
    base_url=os.getenv("GROK_BASE_URL")
)

MODEL = os.getenv("GROK_MODEL")


def analizar_respuesta(
    pregunta,
    respuesta_correcta,
    respuesta_estudiante
):
    prompt = crear_prompt(
        pregunta,
        respuesta_correcta,
        respuesta_estudiante
    )

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "Eres NEXA, un agente educativo especializado "
                    "en detectar dificultades de aprendizaje y "
                    "proponer intervenciones pedagógicas."
                )
            },
            {
                "role": "user",
                "content": prompt
            }
        ]
    )

    return response.choices[0].message.content

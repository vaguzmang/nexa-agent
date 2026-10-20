import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

api_key = os.getenv("GROK_API_KEY")
base_url = os.getenv("GROK_BASE_URL")
model = os.getenv("GROK_MODEL")

if not api_key:
    raise ValueError("No se encontró GROK_API_KEY en .env")

if not base_url:
    raise ValueError("No se encontró GROK_BASE_URL en .env")

if not model:
    raise ValueError("No se encontró GROK_MODEL en .env")

client = OpenAI(
    api_key=api_key,
    base_url=base_url
)

print("Conectando NEXA con Grok...")
print(f"Modelo configurado: {model}")

response = client.chat.completions.create(
    model=model,
    messages=[
        {
            "role": "system",
            "content": (
                "Eres NEXA, un agente educativo especializado "
                "en detectar dificultades de aprendizaje."
            )
        },
        {
            "role": "user",
            "content": (
                "Un estudiante recibió la pregunta: ¿Cuánto es 12 x 8? "
                "La respuesta correcta es 96, pero respondió 84. "
                "Identifica brevemente el posible error y propone "
                "una intervención educativa corta."
            )
        }
    ]
)

print("\n=== RESPUESTA DE GROK ===\n")
print(response.choices[0].message.content)
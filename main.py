from grok_client import analizar_respuesta

print("\n==============================")
print(" NEXA - Diagnóstico educativo")
print("==============================\n")

pregunta = input("Pregunta: ")
respuesta_correcta = input("Respuesta correcta: ")
respuesta_estudiante = input("Respuesta del estudiante: ")

print("\nNEXA está analizando la respuesta...\n")

resultado = analizar_respuesta(
    pregunta,
    respuesta_correcta,
    respuesta_estudiante
)

print("=== RESULTADO DE NEXA ===\n")
print(resultado)

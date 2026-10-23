from dataclasses import asdict
import json

from grok_client import DiagnosisGenerationError, analizar_respuesta

print("\n==============================")
print(" NEXA - Diagnóstico educativo")
print("==============================\n")

actividad = input("Actividad o pregunta a evaluar: ")
respuesta_estudiante = input("Respuesta del estudiante: ")

print("\nNEXA está analizando la respuesta...\n")

try:
    resultado, meta = analizar_respuesta(
        actividad,
        respuesta_estudiante,
    )
except DiagnosisGenerationError as error:
    print("=== NEXA NO PUDO VALIDAR EL DIAGNÓSTICO ===\n")
    print(error)
    print("\n=== METADATOS TÉCNICOS SEGUROS ===\n")
    print(json.dumps(asdict(error.meta), ensure_ascii=False, indent=2))
else:
    print("=== RESULTADO DE NEXA ===\n")
    print(resultado.model_dump_json(indent=2))
    print("\n=== METADATOS TÉCNICOS SEGUROS ===\n")
    print(json.dumps(asdict(meta), ensure_ascii=False, indent=2))

from dataclasses import asdict
import json

from grok_client import DiagnosisGenerationError, analizar_respuesta
from s2.agent import S2AgentError, run_learning_agent


print("\n================================")
print(" NEXA S2 - Agente de aprendizaje")
print("================================\n")

student_id = input("ID del estudiante: ").strip()
activity = input("Actividad o pregunta: ").strip()
student_answer = input("Respuesta del estudiante: ").strip()

print("\n1) NEXA diagnostica la evidencia con diag.v1.1...\n")

try:
    diagnosis, diagnosis_meta = analizar_respuesta(
        activity,
        student_answer,
    )
except DiagnosisGenerationError as error:
    print("No fue posible producir un diagnóstico válido.")
    print(json.dumps(asdict(error.meta), ensure_ascii=False, indent=2))
    raise SystemExit(1)

print(diagnosis.model_dump_json(indent=2))

print("\n2) Grok decide qué herramientas necesita NEXA...\n")

try:
    final_response, agent_meta = run_learning_agent(
        student_id=student_id,
        activity=activity,
        student_answer=student_answer,
        diagnosis=diagnosis,
    )
except S2AgentError as error:
    print("=== ERROR CONTROLADO DEL AGENTE S2 ===")
    print(error)
    print(json.dumps(asdict(error.meta), ensure_ascii=False, indent=2))
    raise SystemExit(2)

print("=== TRAZA DE HERRAMIENTAS ===\n")
for index, trace in enumerate(agent_meta.tools, start=1):
    print(f"[{index}] {trace.name}")
    print("argumentos:")
    print(json.dumps(trace.arguments, ensure_ascii=False, indent=2))
    print("resultado:")
    print(json.dumps(trace.result, ensure_ascii=False, indent=2))
    print()

print("=== RESPUESTA DE NEXA AL ESTUDIANTE ===\n")
print(final_response)

print("\n=== METADATOS S2 ===\n")
print(
    json.dumps(
        {
            "tool_calls_count": len(agent_meta.tools),
            "tool_names": [trace.name for trace in agent_meta.tools],
            "llm_calls_count": len(agent_meta.calls),
            "total_tokens": agent_meta.total_tokens,
            "total_latency_ms": agent_meta.total_latency_ms,
            "calls": [asdict(call) for call in agent_meta.calls],
        },
        ensure_ascii=False,
        indent=2,
    )
)

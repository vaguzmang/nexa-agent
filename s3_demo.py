from dataclasses import asdict
import json

from grok_client import DiagnosisGenerationError
from s2.agent import S2AgentError
from s3.session import run_student_turn


print("\n========================================")
print(" NEXA S3 LOCAL - Intake + Objective Resolver")
print("========================================\n")

student_id = input("ID del estudiante: ").strip()
activity = input(
    "Actividad/pregunta previa del curso o profesor "
    "(Enter si es consulta libre): "
).strip() or None
message = input("Mensaje del estudiante: ").strip()

try:
    result = run_student_turn(
        student_id=student_id,
        message=message,
        activity=activity,
    )
except DiagnosisGenerationError as error:
    print("=== ERROR CONTROLADO DE DIAGNÓSTICO ===")
    print(error)
    print(json.dumps(asdict(error.meta), ensure_ascii=False, indent=2))
    raise SystemExit(1)
except S2AgentError as error:
    print("=== ERROR CONTROLADO DEL AGENTE ===")
    print(error)
    print(json.dumps(asdict(error.meta), ensure_ascii=False, indent=2))
    raise SystemExit(2)

print("\n=== LEARNING INTAKE ===\n")
print(json.dumps(result.intake.as_dict(), ensure_ascii=False, indent=2))

print("\n=== OBJECTIVE RESOLVER (INTERNO) ===\n")
print(json.dumps(result.objective_resolution.as_dict(), ensure_ascii=False, indent=2))

print("\n=== SAFEGUARDING GATE (NO CLÍNICO) ===\n")
print(json.dumps(result.safeguarding.as_dict(), ensure_ascii=False, indent=2))

print("\n=== DIAGNÓSTICO ===\n")
if result.diagnosis_meta is None:
    print("diag.v1.1 OMITIDO: el turno no contenía un intento evaluable.")
    print(json.dumps(result.diagnosis, ensure_ascii=False, indent=2))
else:
    if hasattr(result.diagnosis, "model_dump"):
        print(result.diagnosis.model_dump_json(indent=2))
    else:
        print(json.dumps(result.diagnosis, ensure_ascii=False, indent=2))

meta = result.agent_meta
print("\n=== OBSERVACIÓN DEL TURNO ===\n")
print(json.dumps(meta.learning_observation, ensure_ascii=False, indent=2))
print("\n=== EVALUACIÓN / INTERRUPCIÓN DEL CICLO ===\n")
print(json.dumps(asdict(meta.cycle_evaluation), ensure_ascii=False, indent=2))
print("\n=== EPISODIO ===\n")
print(json.dumps({
    "task_id": meta.task_id,
    "episode_id": meta.episode_id,
    "episode_status": meta.episode_status,
    "episode_action": meta.episode_action,
    "learning_delta": meta.learning_delta,
    "interaction_need": meta.interaction_need,
    "objective_action": meta.objective_action,
}, ensure_ascii=False, indent=2))

print("\n=== TRAZA DE HERRAMIENTAS (SNAPSHOTS INTERMEDIOS) ===\n")
for index, trace in enumerate(meta.tools, start=1):
    print(f"[{index}] {trace.name}")
    print("argumentos:")
    print(json.dumps(trace.arguments, ensure_ascii=False, indent=2))
    print("resultado:")
    print(json.dumps(trace.result, ensure_ascii=False, indent=2))
    print()

record_trace = next(
    (trace for trace in reversed(meta.tools)
     if trace.name == "record_learning_event"
     and isinstance(trace.arguments, dict)
     and trace.result.get("ok")),
    None,
)
if record_trace is not None:
    args = record_trace.arguments
    print("=== DECISIÓN PEDAGÓGICA ===\n")
    print(json.dumps({
        "task_type": args.get("task_type"),
        "response_format": args.get("response_format"),
        "retrieval_required": args.get("retrieval_required"),
        "transfer_context": args.get("transfer_context"),
        "incoming_evidence_support": args.get("support_level"),
        "intervention_support_level": args.get("intervention_support_level"),
        "planner_top_strategy": args.get("planner_top_strategy"),
        "selected_strategy": args.get("strategy_type"),
        "selection_mode": args.get("selection_mode"),
        "selection_reason_code": args.get("selection_reason_code"),
        "selection_reason": args.get("selection_reason"),
    }, ensure_ascii=False, indent=2))
    print()

print("=== RESPUESTA DE NEXA AL ESTUDIANTE ===\n")
print(result.response)

print("\n=== MÉTRICAS END-TO-END S3 ===\n")
print(json.dumps(result.metrics, ensure_ascii=False, indent=2))
if result.metrics["estimated_cost_usd"] is None:
    print(
        "\nCosto USD: no calculado. Configura GROK_INPUT_USD_PER_MILLION "
        "y GROK_OUTPUT_USD_PER_MILLION cuando Platika/modelo defina tarifas aplicables."
    )

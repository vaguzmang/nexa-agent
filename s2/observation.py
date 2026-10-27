import json
import re
import unicodedata
from dataclasses import asdict, dataclass


_STRATEGY_SUPPORT = {
    "probe": "low",
    "hint": "low",
    "contrast_example": "medium",
    "analogy": "medium",
    "guided_practice": "medium",
    "worked_example": "high",
    "concept_explanation": "high",
    "prerequisite_review": "high",
    "independent_practice": "none",
}


@dataclass(frozen=True)
class TurnObservation:
    turn_type: str
    evidence_eligible: bool
    task_type: str
    response_format: str
    retrieval_required: bool
    transfer_context: bool
    evidence_mode: str
    independent_evidence_eligible: bool
    support_level: str
    difficulty_relation: str
    evidence_profile: str | None

    def as_dict(self):
        return asdict(self)


def _normalize(text):
    text = unicodedata.normalize("NFKD", str(text or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", text.casefold()).strip()


def classify_turn_type(answer):
    raw = str(answer or "").strip()
    text = _normalize(raw)
    if not text:
        return "mixed"

    if len(text) <= 28 and text in {"hola", "gracias", "ok", "listo", "vale", "perfecto"}:
        return "off_topic"

    confirmation = (
        "esta bien",
        "es correcto",
        "voy bien",
        "cierto",
        "verdad",
        "lo hice bien",
    )
    if any(term in text for term in confirmation) and ("?" in raw or len(text) < 90):
        return "confirmation"

    learning_request = (
        "quiero aprender", "quiero entender", "quiero saber", "enseñame", "ensename",
        "me gustaria aprender", "ayudame a aprender", "quiero estudiar",
    )
    if any(term in text for term in learning_request):
        return "learning_request"

    hint = ("dame una pista", "una pista", "ayudame", "orientame", "una ayuda")
    if any(term in text for term in hint):
        return "request_hint"

    explanation = (
        "explicame",
        "explica otra vez",
        "explicalo otra vez",
        "no entiendo",
        "no entendi",
        "repite",
        "otro ejemplo",
        "puedes explicar",
        "me lo explicas",
    )
    if any(term in text for term in explanation):
        return "request_explanation"

    meta = (
        "no recuerdo",
        "se me olvido",
        "no estoy seguro",
        "no estoy segura",
        "creo que olvide",
        "creo que no recuerdo",
    )
    if any(term in text for term in meta) and len(text) < 120:
        return "metacognitive"

    # Una pregunta explícita no se usa como evidencia de desempeño por defecto.
    if "?" in raw:
        return "question"

    question_starts = (
        "que ", "como ", "por que ", "cuando ", "donde ", "cual ",
        "puedo ", "puedes ", "debo ", "seria ",
    )
    if text.startswith(question_starts):
        return "question"

    return "attempt"


def strategy_support_level(strategy_type):
    return _STRATEGY_SUPPORT.get(strategy_type, "unknown")


def _contains_any(text, terms):
    return any(re.search(r"(?<!\\w)" + re.escape(term) + r"(?!\\w)", text) for term in terms)


def _infer_task_axes(activity, student_answer, diagnosis):
    """Separa naturaleza cognitiva, formato y flags de retrieval/transfer."""
    evidence = diagnosis.get("evidence") or {}
    gap = diagnosis.get("gap") or {}
    evidence_type = evidence.get("type")
    combined = _normalize(f"{activity or ''} {student_answer or ''}")

    procedural_markers = (
        "resolver", "resuelve", "calcular", "calcula", "despejar", "despeja",
        "simplificar", "simplifica", "factorizar", "factoriza", "procedimiento",
        "paso a paso", "algoritmo", "programar", "programa", "implementar",
        "depurar", "corrige el codigo", "corregir el codigo",
    )
    conceptual_markers = (
        "por que", "porque", "explica por que", "explicar por que",
        "significa", "concepto", "sentido", "que es", "qué es",
    )
    retrieval_markers = (
        "recuerda", "recordar", "memoriza", "memorizar", "enumera", "nombra",
        "lista", "cual es la definicion", "define ", "que significa exactamente",
    )
    transfer_markers = (
        "aplica", "aplicar", "transfiere", "transferir", "otro contexto",
        "situacion diferente", "caso nuevo", "problema nuevo", "contexto nuevo",
        "en otro caso", "en una situacion nueva",
    )

    procedural = _contains_any(combined, procedural_markers) or gap.get("type") == "incomplete_procedure"
    conceptual = _contains_any(combined, conceptual_markers)

    if procedural and conceptual:
        task_type = "mixed"
    elif procedural:
        task_type = "procedural"
    elif conceptual or evidence_type in {"open_ended", "rubric"}:
        task_type = "conceptual"
    else:
        task_type = "unknown"

    if evidence_type == "closed_ended":
        response_format = "closed"
    elif evidence_type in {"open_ended", "rubric"}:
        response_format = "open"
    else:
        response_format = "not_applicable"

    return (
        task_type,
        response_format,
        _contains_any(combined, retrieval_markers),
        _contains_any(combined, transfer_markers),
    )

def _evidence_profile(diagnosis):
    criteria = (diagnosis.get("evidence") or {}).get("criteria")
    if not criteria:
        return None
    compact = []
    for item in criteria:
        if not isinstance(item, dict):
            continue
        compact.append({
            "name": str(item.get("name") or "")[:180],
            "result": str(item.get("result") or "")[:40],
        })
    return json.dumps(compact, ensure_ascii=False) if compact else None


def observe_turn(
    *,
    activity,
    student_answer,
    diagnosis,
    pending_intervention=None,
    difficulty_relation="unknown",
    task_type=None,
    evidence_mode=None,
    support_level=None,
    turn_type_override=None,
    evidence_eligible_override=None,
):
    """Capa conservadora previa a la atribución pedagógica.

    No sustituye diag.v1.1. Decide si el turno actual es una evidencia elegible
    para cerrar una intervención anterior. Ante duda, preserva la intervención.
    """
    diagnosis_dict = diagnosis.model_dump() if hasattr(diagnosis, "model_dump") else dict(diagnosis)
    turn_type = turn_type_override or classify_turn_type(student_answer)
    evidence_result = (diagnosis_dict.get("evidence") or {}).get("result")
    evidence_eligible = turn_type == "attempt" and evidence_result != "insufficient_evidence"
    if evidence_eligible_override is not None:
        evidence_eligible = bool(evidence_eligible_override)

    inferred_task_type, inferred_response_format, retrieval_required, transfer_context = _infer_task_axes(
        activity, student_answer, diagnosis_dict
    )
    inferred_task_type = task_type or inferred_task_type

    # evidence_mode/support_level describen la EVIDENCIA ENTRANTE, no la ayuda
    # que NEXA está a punto de ofrecer. Si no hay intento evaluable, no debemos
    # etiquetar el turno como evidencia independiente o guiada.
    if evidence_mode is None:
        if not evidence_eligible:
            evidence_mode = "not_applicable"
        elif pending_intervention:
            previous_strategy = pending_intervention.get("strategy_type")
            previous_support = _STRATEGY_SUPPORT.get(previous_strategy, "unknown")
            evidence_mode = "independent" if previous_support == "none" else "guided"
        else:
            evidence_mode = "independent"

    if support_level is None:
        if not evidence_eligible:
            support_level = "not_applicable"
        elif pending_intervention:
            support_level = _STRATEGY_SUPPORT.get(
                pending_intervention.get("strategy_type"), "unknown"
            )
        else:
            support_level = "none"

    allowed_relations = {
        "same_context", "similar_context", "transfer_context", "higher_difficulty",
        "new_context", "unknown"
    }
    relation = difficulty_relation if difficulty_relation in allowed_relations else "unknown"

    return TurnObservation(
        turn_type=turn_type,
        evidence_eligible=evidence_eligible,
        task_type=inferred_task_type,
        response_format=inferred_response_format,
        retrieval_required=retrieval_required,
        transfer_context=transfer_context,
        evidence_mode=evidence_mode,
        independent_evidence_eligible=(evidence_mode == "independent"),
        support_level=support_level,
        difficulty_relation=relation,
        evidence_profile=_evidence_profile(diagnosis_dict),
    )

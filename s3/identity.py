from dataclasses import dataclass


AGENT_IDENTITY_STATEMENT = (
    "NEXA es un agente educativo. Observa el contexto del aprendizaje, usa herramientas "
    "y fuentes autorizadas, toma decisiones pedagógicas dentro de sus límites, acompaña "
    "al estudiante, aprende de evidencia posterior y coordina con humanos o sistemas "
    "externos cuando corresponde. No es un LMS, sistema clínico, ERP académico ni BI."
)

AGENT_CAPABILITIES = frozenset({
    "read_learning_memory",
    "write_learning_events",
    "select_pedagogical_strategy",
    "use_authorized_learning_resources",
    "produce_teacher_summary",
    "emit_human_review_signal",
    "query_aggregate_learning_analytics",
})

NON_AGENT_CORE_PRODUCTS = frozenset({
    "lms_course_management",
    "video_library_management",
    "student_enrollment_management",
    "clinical_case_management",
    "institutional_bi_dashboard",
})


@dataclass(frozen=True)
class AgentBoundaryDecision:
    capability: str
    allowed_in_agent_core: bool
    reason: str


def evaluate_agent_boundary(capability: str) -> AgentBoundaryDecision:
    key = str(capability or "").strip()
    if key in NON_AGENT_CORE_PRODUCTS:
        return AgentBoundaryDecision(
            capability=key,
            allowed_in_agent_core=False,
            reason="Debe implementarse como sistema o integración externa; NEXA solo puede consumirla como capacidad.",
        )
    return AgentBoundaryDecision(
        capability=key,
        allowed_in_agent_core=True,
        reason="Puede expresarse como una capacidad del agente sin convertir a NEXA en otra plataforma.",
    )

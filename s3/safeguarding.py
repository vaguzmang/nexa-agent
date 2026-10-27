from dataclasses import asdict, dataclass
import re
import unicodedata


@dataclass(frozen=True)
class SafeguardingAssessment:
    level: str
    requires_human_review: bool
    pause_academic_flow: bool
    concern_type: str | None
    rationale: str

    def as_dict(self):
        return asdict(self)


def _norm(text):
    value = unicodedata.normalize("NFKD", str(text or ""))
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", value.casefold()).strip()


def assess_safeguarding(message: str) -> SafeguardingAssessment:
    """Gate conservador. Detecta señales explícitas; nunca produce diagnóstico clínico."""
    text = _norm(message)
    urgent = (
        "me quiero matar", "quiero matarme", "hacerme dano", "hacerme daño",
        "no quiero vivir", "suicid", "me estan pegando", "me pegan en casa",
        "me hacen dano en casa", "me hacen daño en casa",
    )
    high = (
        "nada vale la pena", "tengo miedo de volver a casa", "me lastiman",
        "violencia en casa", "me golpean", "abuso",
    )
    supportive = (
        "soy bruto", "soy estupido", "soy estúpido", "no sirvo para",
        "nunca voy a aprender", "estoy muy triste", "no puedo concentrarme",
        "estoy agotado", "me siento muy mal",
    )

    if any(token in text for token in urgent):
        return SafeguardingAssessment(
            level="urgent", requires_human_review=True, pause_academic_flow=True,
            concern_type="explicit_safety_signal",
            rationale="Señal explícita de posible riesgo; requiere revisión humana según política institucional.",
        )
    if any(token in text for token in high):
        return SafeguardingAssessment(
            level="high", requires_human_review=True, pause_academic_flow=False,
            concern_type="serious_wellbeing_signal",
            rationale="Señal seria de bienestar o seguridad; NEXA no diagnostica y recomienda revisión humana.",
        )
    if any(token in text for token in supportive):
        return SafeguardingAssessment(
            level="supportive_learning", requires_human_review=False, pause_academic_flow=False,
            concern_type="learning_distress_signal",
            rationale="Señal de frustración/malestar que debe adaptar el acompañamiento sin diagnóstico clínico.",
        )
    return SafeguardingAssessment(
        level="none", requires_human_review=False, pause_academic_flow=False,
        concern_type=None, rationale="Sin señal explícita que cambie la política de acompañamiento.",
    )

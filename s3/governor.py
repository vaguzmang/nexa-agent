from dataclasses import asdict, dataclass
import re


@dataclass(frozen=True)
class GovernorResult:
    text: str
    changed: bool
    interventions: tuple[str, ...]

    def as_dict(self):
        return asdict(self)


def govern_student_response(text, *, objective_source="inferred", strategy_evidence_exposures=0):
    """Guardrail estrecho de claims. No reescribe pedagogía salvo afirmaciones no sustentadas."""
    output = str(text or "")
    interventions = []

    replacements = [
        (r"(?i)\b(ya\s+)?(dominas|dominaste|has dominado)\s+(el\s+)?(tema|contenido|objetivo)\b",
         "hay evidencia positiva en este episodio", "blocked_mastery_claim"),
        (r"(?i)\b(tienes|padeces)\s+(depresion|depresión|ansiedad|tdah|dislexia|trauma)\b",
         "lo que describes puede estar haciendo más difícil aprender en este momento", "blocked_clinical_diagnosis"),
    ]
    for pattern, replacement, code in replacements:
        new = re.sub(pattern, replacement, output)
        if new != output:
            output = new
            interventions.append(code)

    if objective_source != "teacher":
        new = re.sub(
            r"(?i)\b(tu profesor|tu profesora|el profesor|la profesora)\s+(dijo|pidio|pidió|quiere|espera)\b",
            "el objetivo actual indica",
            output,
        )
        if new != output:
            output = new
            interventions.append("blocked_false_teacher_attribution")

    if strategy_evidence_exposures < 5:
        new = re.sub(
            r"(?i)\b(esta|esa)\s+estrategia\s+(es|parece ser)\s+la\s+que\s+mejor\s+te\s+funciona\b",
            "esta estrategia ha mostrado una señal preliminar de ayuda en este contexto",
            output,
        )
        if new != output:
            output = new
            interventions.append("softened_strategy_preference_claim")

    return GovernorResult(output, bool(interventions), tuple(interventions))

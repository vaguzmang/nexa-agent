import hashlib
import re
import unicodedata
from dataclasses import asdict, dataclass

from s2.episodes import list_recent_episodes
from s2.observation import classify_turn_type


@dataclass(frozen=True)
class LearningIntake:
    turn_type: str
    interaction_need: str
    should_diagnose: bool
    diagnosis_target: str | None
    has_activity_context: bool

    def as_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class ObjectiveResolution:
    objective_id: str
    objective: str
    objective_source: str
    action: str
    matched_episode_id: str | None
    similarity: float | None

    def as_dict(self):
        return asdict(self)


def _normalize(text):
    normalized = unicodedata.normalize("NFKD", str(text or ""))
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", normalized.casefold()).strip()


def _tokens(text):
    stop = {
        "el", "la", "los", "las", "de", "del", "y", "o", "en", "un", "una",
        "que", "se", "con", "por", "para", "antes", "despues", "como", "al",
        "quiero", "aprender", "entender", "saber", "explica", "explicame", "sobre",
        "puedes", "puedo", "me", "lo", "otra", "vez", "cual", "cuando", "donde",
    }
    return {
        token
        for token in re.findall(r"[a-z0-9]+", _normalize(text))
        if len(token) > 2 and token not in stop
    }


def objective_similarity(a, b):
    left = _tokens(a)
    right = _tokens(b)
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _contains_marker(text, marker):
    # Límites de palabra evitan falsos positivos como "eso" dentro de "resolver".
    pattern = r"(?<!\w)" + re.escape(marker) + r"(?!\w)"
    return re.search(pattern, text) is not None


def _is_referential_followup(message):
    text = _normalize(message)
    markers = (
        "otra vez", "esa parte", "eso", "esto", "lo anterior", "lo de antes",
        "no recuerdo", "se me olvido", "no entiendo", "me lo explicas", "esa duda",
    )
    return any(_contains_marker(text, marker) for marker in markers)


def _is_explicit_topic_switch(message):
    text = _normalize(message)
    markers = (
        "ahora quiero aprender", "ahora quiero saber", "ahora quiero entender",
        "cambiemos de tema", "cambiar de tema", "otro tema", "otra materia",
        "pasemos a", "ahora sobre", "ahora necesito aprender",
    )
    return any(_contains_marker(text, marker) for marker in markers)


def _is_explicit_return_request(message):
    """Detecta intención explícita de volver a un tema previo.

    Esta señal debe resolverse contra episodios históricos antes de aplicar
    referencias vagas como "no recuerdo", porque esas referencias por sí solas
    no identifican el objetivo al que el alumno quiere volver.
    """
    text = _normalize(message)
    markers = (
        "volvamos a", "volver a", "volvamos con", "volver con",
        "retomemos", "retomar", "regresemos a", "regresar a",
        "quiero volver a", "quiero retomar", "de nuevo con",
    )
    return any(_contains_marker(text, marker) for marker in markers)


def _objective_label(seed):
    raw = re.sub(r"\s+", " ", str(seed or "").strip()).strip(" ¿?¡!.,:;")
    if not raw:
        return "Objetivo de aprendizaje inferido"

    normalized = _normalize(raw)
    prefixes = [
        "ahora quiero aprender ", "ahora quiero entender ", "ahora quiero saber ",
        "quiero aprender ", "quiero entender ", "quiero saber ", "me gustaria aprender ",
        "ensename ", "explicame ", "puedes explicarme ", "que es ", "por que ",
    ]
    cleaned = raw
    for prefix in prefixes:
        if normalized.startswith(prefix):
            # Remove approximately the same number of words from the original text.
            count = len(prefix.split())
            cleaned = " ".join(raw.split()[count:]).strip(" ¿?¡!.,:;") or raw
            break

    if len(cleaned) > 220:
        cleaned = cleaned[:217].rstrip() + "..."
    return f"Comprender: {cleaned}"


def _inferred_objective_id(label):
    canonical = _normalize(label)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
    return f"inferred-{digest}"


def classify_learning_intake(*, message, activity=None, state=None):
    state = state or {}
    turn_type = classify_turn_type(message)
    pending = state.get("pending_intervention")
    has_activity = bool(str(activity or "").strip())

    if turn_type == "attempt" and (has_activity or pending):
        should_diagnose = True
        diagnosis_target = str(activity or "").strip() or pending.get("objective")
        interaction_need = "diagnostic_gap"
    else:
        should_diagnose = False
        diagnosis_target = None
        interaction_need = {
            "learning_request": "explanation",
            "question": "explanation",
            "request_explanation": "explanation",
            "request_hint": "hint",
            "confirmation": "confirmation",
            "metacognitive": "reassessment",
            "off_topic": "none",
            "mixed": "exploration",
            "attempt": "exploration",
        }.get(turn_type, "exploration")

    return LearningIntake(
        turn_type=turn_type,
        interaction_need=interaction_need,
        should_diagnose=should_diagnose,
        diagnosis_target=diagnosis_target,
        has_activity_context=has_activity,
    )


def resolve_objective(
    *,
    student_id,
    message,
    activity=None,
    intake,
    state=None,
    objective_id=None,
    objective_source=None,
    objective_label=None,
    db_path=None,
):
    """Resuelve objetivo sin pedir IDs internos al alumno.

    Decisiones válidas:
    create_inferred | continue_existing | switch_objective |
    resume_suspended | reopen_closed.
    """
    state = state or {}
    active = state.get("active_episode") or {}
    pending = state.get("pending_intervention") or {}
    query = " ".join(
        part for part in [str(activity or "").strip(), str(message or "").strip()]
        if part
    )
    explicit_switch = _is_explicit_topic_switch(message)
    explicit_return = _is_explicit_return_request(message)

    if objective_id:
        source = objective_source or "inferred"
        label = objective_label or _objective_label(activity or message)
        episodes = list_recent_episodes(student_id, limit=20, db_path=db_path)
        matched = next((ep for ep in episodes if ep.get("objective_id") == str(objective_id)), None)
        if matched:
            if matched.get("status") == "suspended":
                action = "resume_suspended"
            elif matched.get("status") in {"evidence_confirmed", "closed"}:
                action = "reopen_closed"
            else:
                action = "continue_existing"
            return ObjectiveResolution(
                objective_id=str(objective_id), objective=objective_label or matched.get("objective") or label,
                objective_source=source, action=action,
                matched_episode_id=matched.get("episode_id"), similarity=None,
            )
        action = "switch_objective" if state.get("current_objective_id") else "create_inferred"
        return ObjectiveResolution(
            objective_id=str(objective_id), objective=label, objective_source=source,
            action=action, matched_episode_id=None, similarity=None,
        )

    # Una petición explícita de RETORNO tiene prioridad sobre referencias vagas
    # al objetivo actual. Ej.: "Volvamos a fotosíntesis. No recuerdo..." no debe
    # convertir "no recuerdo" en continuidad del tema que estaba activo.
    if explicit_return:
        episodes = list_recent_episodes(student_id, limit=20, db_path=db_path)
        current_id = state.get("current_objective_id") or active.get("objective_id")
        prior_best = None
        prior_best_score = 0.0
        for episode in episodes:
            if current_id and episode.get("objective_id") == current_id:
                continue
            score = objective_similarity(query, episode.get("objective"))
            if score > prior_best_score:
                prior_best_score = score
                prior_best = episode

        if prior_best is not None and prior_best_score >= 0.10:
            if prior_best.get("status") == "suspended":
                action = "resume_suspended"
            elif prior_best.get("status") in {"evidence_confirmed", "closed"}:
                action = "reopen_closed"
            else:
                action = "continue_existing"
            return ObjectiveResolution(
                objective_id=prior_best["objective_id"],
                objective=prior_best["objective"],
                objective_source=prior_best.get("objective_source") or "inferred",
                action=action,
                matched_episode_id=prior_best.get("episode_id"),
                similarity=round(prior_best_score, 4),
            )

    # La continuidad solo se permite con señal real de similitud o referencia explícita.
    # Una orden explícita de cambio de tema invalida la continuidad del objetivo activo.
    # Una petición explícita de retorno que NO encontró tema previo tampoco puede
    # usar una referencia vaga ("no recuerdo") para quedarse por accidente en el
    # objetivo actual; en ese caso exigimos similitud léxica real.
    if pending:
        sim = objective_similarity(query, pending.get("objective"))
        if sim >= 0.08 or (
            _is_referential_followup(message)
            and not explicit_switch
            and not explicit_return
        ):
            return ObjectiveResolution(
                objective_id=pending["objective_id"],
                objective=pending["objective"],
                objective_source=pending.get("objective_source") or "inferred",
                action="continue_existing",
                matched_episode_id=pending.get("episode_id"),
                similarity=round(sim, 4),
            )

    if active:
        sim = objective_similarity(query, active.get("objective"))
        if sim >= 0.08 or (
            _is_referential_followup(message)
            and not explicit_switch
            and not explicit_return
        ):
            if active.get("status") == "suspended":
                action = "resume_suspended"
            elif active.get("status") in {"evidence_confirmed", "closed"}:
                action = "reopen_closed"
            else:
                action = "continue_existing"
            return ObjectiveResolution(
                objective_id=active["objective_id"],
                objective=active["objective"],
                objective_source=active.get("objective_source") or "inferred",
                action=action,
                matched_episode_id=active.get("episode_id"),
                similarity=round(sim, 4),
            )

    episodes = list_recent_episodes(student_id, limit=20, db_path=db_path)
    best = None
    best_score = 0.0
    for episode in episodes:
        score = objective_similarity(query, episode.get("objective"))
        if score > best_score:
            best_score = score
            best = episode

    if best is not None and best_score >= 0.10:
        if best.get("status") == "suspended":
            action = "resume_suspended"
        elif best.get("status") in {"evidence_confirmed", "closed"}:
            action = "reopen_closed"
        else:
            action = "continue_existing"
        return ObjectiveResolution(
            objective_id=best["objective_id"],
            objective=best["objective"],
            objective_source=best.get("objective_source") or "inferred",
            action=action,
            matched_episode_id=best.get("episode_id"),
            similarity=round(best_score, 4),
        )

    label = objective_label or _objective_label(activity or message)
    has_existing_context = bool(state.get("current_objective_id") or active or episodes)
    action = "switch_objective" if has_existing_context else "create_inferred"
    return ObjectiveResolution(
        objective_id=_inferred_objective_id(label),
        objective=label,
        objective_source="inferred",
        action=action,
        matched_episode_id=None,
        similarity=round(best_score, 4) if episodes else None,
    )


import hashlib
import os
from dataclasses import dataclass, replace
from time import perf_counter
from typing import Literal

from dotenv import load_dotenv
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    OpenAI,
    RateLimitError,
)
from pydantic import ValidationError

from prompt import SYSTEM_PROMPT, crear_prompt, crear_prompt_reparacion
from schemas.diagnosis import DiagnosisResult


REQUEST_TIMEOUT_SECONDS = 120.0

CallOutcome = Literal[
    "success",
    "transport_error",
    "invalid_output",
]

OperationResult = Literal[
    "success",
    "repaired",
    "transport_error",
    "invalid_output",
]

ErrorClass = Literal[
    "auth",
    "rate_limit",
    "timeout",
    "connection",
    "http",
    "empty_content",
    "truncated",
    "content_filter",
    "json",
    "schema",
]


@dataclass(frozen=True)
class LlmCallMeta:
    attempt: int
    kind: Literal["primary", "repair"]
    requested_model: str
    reported_model: str | None
    finish_reason: str | None
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None
    latency_ms: int
    outcome: CallOutcome
    error_class: ErrorClass | None
    http_status: int | None
    truncated: bool


@dataclass(frozen=True)
class DiagnosisTransportMeta:
    result: OperationResult
    calls: tuple[LlmCallMeta, ...]
    total_latency_ms: int
    total_tokens: int | None
    input_char_count: int
    input_sha256_16: str


class DiagnosisGenerationError(RuntimeError):
    """NEXA no pudo producir un diagnóstico válido o transportarlo de forma segura."""

    def __init__(self, message: str, *, meta: DiagnosisTransportMeta):
        super().__init__(message)
        self.meta = meta


def _create_client():
    load_dotenv()

    return OpenAI(
        api_key=os.getenv("GROK_API_KEY"),
        base_url=os.getenv("GROK_BASE_URL"),
        max_retries=0,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )


def _safe_nonnegative_int(value):
    return value if type(value) is int and value >= 0 else None


def _response_usage(response):
    usage = getattr(response, "usage", None)

    return (
        _safe_nonnegative_int(getattr(usage, "prompt_tokens", None)),
        _safe_nonnegative_int(getattr(usage, "completion_tokens", None)),
        _safe_nonnegative_int(getattr(usage, "total_tokens", None)),
    )


def _http_status(error):
    value = getattr(error, "status_code", None)
    return value if type(value) is int else None


def _call_meta(
    *,
    attempt,
    kind,
    requested_model,
    latency_ms,
    outcome,
    error_class=None,
    http_status=None,
    response=None,
    truncated=False,
):
    prompt_tokens = None
    completion_tokens = None
    total_tokens = None
    reported_model = None
    finish_reason = None

    if response is not None:
        reported_model = getattr(response, "model", None)
        prompt_tokens, completion_tokens, total_tokens = _response_usage(response)

        choices = getattr(response, "choices", None)
        if choices:
            finish_reason = getattr(choices[0], "finish_reason", None)

    return LlmCallMeta(
        attempt=attempt,
        kind=kind,
        requested_model=requested_model,
        reported_model=reported_model,
        finish_reason=finish_reason,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        latency_ms=latency_ms,
        outcome=outcome,
        error_class=error_class,
        http_status=http_status,
        truncated=truncated,
    )


def _request_completion(messages, *, attempt, kind, client=None):
    active_client = client or _create_client()
    model = os.getenv("GROK_MODEL") or ""
    started = perf_counter()

    try:
        response = active_client.chat.completions.create(
            model=model,
            messages=messages,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except AuthenticationError as error:
        latency_ms = round((perf_counter() - started) * 1000)
        return None, _call_meta(
            attempt=attempt,
            kind=kind,
            requested_model=model,
            latency_ms=latency_ms,
            outcome="transport_error",
            error_class="auth",
            http_status=_http_status(error),
        )
    except RateLimitError as error:
        latency_ms = round((perf_counter() - started) * 1000)
        return None, _call_meta(
            attempt=attempt,
            kind=kind,
            requested_model=model,
            latency_ms=latency_ms,
            outcome="transport_error",
            error_class="rate_limit",
            http_status=_http_status(error),
        )
    except APITimeoutError as error:
        latency_ms = round((perf_counter() - started) * 1000)
        return None, _call_meta(
            attempt=attempt,
            kind=kind,
            requested_model=model,
            latency_ms=latency_ms,
            outcome="transport_error",
            error_class="timeout",
            http_status=_http_status(error),
        )
    except APIConnectionError as error:
        latency_ms = round((perf_counter() - started) * 1000)
        return None, _call_meta(
            attempt=attempt,
            kind=kind,
            requested_model=model,
            latency_ms=latency_ms,
            outcome="transport_error",
            error_class="connection",
            http_status=_http_status(error),
        )
    except APIStatusError as error:
        latency_ms = round((perf_counter() - started) * 1000)
        return None, _call_meta(
            attempt=attempt,
            kind=kind,
            requested_model=model,
            latency_ms=latency_ms,
            outcome="transport_error",
            error_class="http",
            http_status=_http_status(error),
        )

    latency_ms = round((perf_counter() - started) * 1000)
    choices = getattr(response, "choices", None)

    if not choices:
        return None, _call_meta(
            attempt=attempt,
            kind=kind,
            requested_model=model,
            latency_ms=latency_ms,
            outcome="invalid_output",
            error_class="empty_content",
            response=response,
        )

    finish_reason = getattr(choices[0], "finish_reason", None)
    message = getattr(choices[0], "message", None)
    content = getattr(message, "content", None)

    if finish_reason == "content_filter":
        return None, _call_meta(
            attempt=attempt,
            kind=kind,
            requested_model=model,
            latency_ms=latency_ms,
            outcome="invalid_output",
            error_class="content_filter",
            response=response,
        )

    if not isinstance(content, str) or not content.strip():
        return None, _call_meta(
            attempt=attempt,
            kind=kind,
            requested_model=model,
            latency_ms=latency_ms,
            outcome="invalid_output",
            error_class="empty_content",
            response=response,
        )

    if finish_reason == "length":
        return content.strip(), _call_meta(
            attempt=attempt,
            kind=kind,
            requested_model=model,
            latency_ms=latency_ms,
            outcome="invalid_output",
            error_class="truncated",
            response=response,
            truncated=True,
        )

    return content.strip(), _call_meta(
        attempt=attempt,
        kind=kind,
        requested_model=model,
        latency_ms=latency_ms,
        outcome="success",
        response=response,
    )


def _validation_error_class(error):
    for item in error.errors():
        if item.get("type") == "json_invalid":
            return "json"
    return "schema"


def _validate_diagnosis(content):
    return DiagnosisResult.model_validate_json(content)


def _operation_meta(*, result, calls, input_text):
    token_values = [call.total_tokens for call in calls]
    total_tokens = (
        sum(token_values)
        if token_values and all(value is not None for value in token_values)
        else None
    )

    digest = hashlib.sha256(input_text.encode("utf-8")).hexdigest()[:16]

    return DiagnosisTransportMeta(
        result=result,
        calls=tuple(calls),
        total_latency_ms=sum(call.latency_ms for call in calls),
        total_tokens=total_tokens,
        input_char_count=len(input_text),
        input_sha256_16=digest,
    )


def _raise_failure(message, *, result, calls, input_text):
    raise DiagnosisGenerationError(
        message,
        meta=_operation_meta(
            result=result,
            calls=calls,
            input_text=input_text,
        ),
    )


def analizar_respuesta(
    pregunta,
    respuesta_estudiante,
    *,
    client=None,
):
    """Genera un diagnóstico validado y telemetría segura, con un único repair lógico."""

    user_prompt = crear_prompt(
        pregunta,
        respuesta_estudiante,
    )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    calls = []

    first_content, first_meta = _request_completion(
        messages,
        attempt=1,
        kind="primary",
        client=client,
    )
    calls.append(first_meta)

    if first_meta.outcome == "transport_error":
        _raise_failure(
            "La llamada primaria a Grok falló en transporte y no se reintentó.",
            result="transport_error",
            calls=calls,
            input_text=user_prompt,
        )

    if first_meta.error_class == "content_filter":
        _raise_failure(
            "Grok filtró la respuesta. No se ejecutó repair.",
            result="invalid_output",
            calls=calls,
            input_text=user_prompt,
        )

    repair_reason = None

    if first_meta.truncated:
        repair_reason = (
            "La salida fue truncada (finish_reason=length). "
            "Devuelve el mismo diagnóstico como JSON completo y compacto."
        )
    elif first_content is None:
        _raise_failure(
            "Grok no devolvió contenido utilizable. No se ejecutó repair.",
            result="invalid_output",
            calls=calls,
            input_text=user_prompt,
        )
    else:
        try:
            result = _validate_diagnosis(first_content)
        except ValidationError as error:
            error_class = _validation_error_class(error)
            calls[0] = replace(
                first_meta,
                outcome="invalid_output",
                error_class=error_class,
            )
            repair_reason = error
        else:
            return result, _operation_meta(
                result="success",
                calls=calls,
                input_text=user_prompt,
            )

    repair_messages = [
        *messages,
        {"role": "assistant", "content": first_content or ""},
        {
            "role": "user",
            "content": crear_prompt_reparacion(repair_reason),
        },
    ]

    repaired_content, repair_meta = _request_completion(
        repair_messages,
        attempt=2,
        kind="repair",
        client=client,
    )
    calls.append(repair_meta)

    if repair_meta.outcome == "transport_error":
        _raise_failure(
            "El repair falló en transporte. No se realizó una tercera llamada.",
            result="transport_error",
            calls=calls,
            input_text=user_prompt,
        )

    if repair_meta.error_class in {
        "content_filter",
        "empty_content",
        "truncated",
    }:
        _raise_failure(
            "El único repair no produjo una salida utilizable. No se realizó una tercera llamada.",
            result="invalid_output",
            calls=calls,
            input_text=user_prompt,
        )

    try:
        result = _validate_diagnosis(repaired_content)
    except ValidationError as error:
        calls[1] = replace(
            repair_meta,
            outcome="invalid_output",
            error_class=_validation_error_class(error),
        )
        _raise_failure(
            "Grok no produjo un DiagnosisResult válido después del único intento de reparación.",
            result="invalid_output",
            calls=calls,
            input_text=user_prompt,
        )

    return result, _operation_meta(
        result="repaired",
        calls=calls,
        input_text=user_prompt,
    )

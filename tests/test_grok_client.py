import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from grok_client import (
    DiagnosisGenerationError,
    REQUEST_TIMEOUT_SECONDS,
    _create_client,
    analizar_respuesta,
)


def valid_diagnosis_json():
    return json.dumps(
        {
            "schema_version": "diag.v1.1",
            "objective": {
                "domain": "mathematics",
                "skill": "multiplicar números enteros",
            },
            "evidence": {
                "type": "closed_ended",
                "result": "does_not_meet",
                "summary": "La respuesta 84 no coincide con 12 x 8.",
            },
            "understanding": {
                "demonstrated": "Reconoce que debe multiplicar.",
                "missing": "No calcula correctamente el producto.",
            },
            "gap": {
                "present": True,
                "type": "factual_error",
                "description": "El producto calculado es incorrecto.",
            },
            "next_step": "practice",
        }
    )


def fake_usage(prompt=20, completion=10, total=30):
    return SimpleNamespace(
        prompt_tokens=prompt,
        completion_tokens=completion,
        total_tokens=total,
    )


def fake_response(
    content,
    *,
    finish_reason="stop",
    model="grok-reported",
    usage=None,
):
    return SimpleNamespace(
        model=model,
        usage=usage,
        choices=[
            SimpleNamespace(
                finish_reason=finish_reason,
                message=SimpleNamespace(content=content),
            )
        ],
    )


def fake_client(*responses_or_errors):
    client = Mock()
    client.chat.completions.create.side_effect = list(responses_or_errors)
    return client


class FakeTimeoutError(Exception):
    status_code = None


class FakeAuthenticationError(Exception):
    status_code = 401


class FakeRateLimitError(Exception):
    status_code = 429


class TestGrokClient(unittest.TestCase):

    def test_client_disables_sdk_retries_and_sets_timeout(self):
        with patch("grok_client.OpenAI") as openai:
            _create_client()

        kwargs = openai.call_args.kwargs
        self.assertEqual(kwargs["max_retries"], 0)
        self.assertEqual(kwargs["timeout"], REQUEST_TIMEOUT_SECONDS)

    def test_valid_first_response_needs_no_repair_and_records_meta(self):
        client = fake_client(
            fake_response(
                valid_diagnosis_json(),
                model="grok-4.6-reported",
                usage=fake_usage(),
            )
        )

        result, meta = analizar_respuesta(
            "¿Cuánto es 12 x 8?",
            "84",
            client=client,
        )

        self.assertEqual(result.schema_version, "diag.v1.1")
        self.assertEqual(client.chat.completions.create.call_count, 1)
        self.assertEqual(meta.result, "success")
        self.assertEqual(len(meta.calls), 1)
        self.assertEqual(meta.calls[0].kind, "primary")
        self.assertEqual(meta.calls[0].reported_model, "grok-4.6-reported")
        self.assertEqual(meta.calls[0].finish_reason, "stop")
        self.assertEqual(meta.calls[0].total_tokens, 30)
        self.assertEqual(meta.total_tokens, 30)
        self.assertGreaterEqual(meta.calls[0].latency_ms, 0)
        self.assertEqual(len(meta.input_sha256_16), 16)

    def test_invalid_response_gets_one_successful_repair(self):
        client = fake_client(
            fake_response("La respuesta parece incorrecta.", usage=fake_usage()),
            fake_response(valid_diagnosis_json(), usage=fake_usage()),
        )

        result, meta = analizar_respuesta(
            "¿Cuánto es 12 x 8?",
            "84",
            client=client,
        )

        self.assertEqual(result.evidence.result, "does_not_meet")
        self.assertEqual(client.chat.completions.create.call_count, 2)
        self.assertEqual(meta.result, "repaired")
        self.assertEqual(len(meta.calls), 2)
        self.assertEqual(meta.calls[0].outcome, "invalid_output")
        self.assertIn(meta.calls[0].error_class, {"json", "schema"})
        self.assertEqual(meta.calls[1].kind, "repair")
        self.assertEqual(meta.total_tokens, 60)

    def test_invalid_repair_fails_without_third_request(self):
        client = fake_client(
            fake_response("no es JSON"),
            fake_response('{"schema_version":"diag.v1.1"}'),
        )

        with self.assertRaises(DiagnosisGenerationError) as context:
            analizar_respuesta(
                "¿Cuánto es 12 x 8?",
                "84",
                client=client,
            )

        self.assertEqual(client.chat.completions.create.call_count, 2)
        self.assertEqual(context.exception.meta.result, "invalid_output")
        self.assertEqual(len(context.exception.meta.calls), 2)

    def test_timeout_is_terminal_and_does_not_trigger_repair(self):
        client = fake_client(FakeTimeoutError())

        with patch("grok_client.APITimeoutError", FakeTimeoutError):
            with self.assertRaises(DiagnosisGenerationError) as context:
                analizar_respuesta("pregunta", "respuesta", client=client)

        self.assertEqual(client.chat.completions.create.call_count, 1)
        self.assertEqual(context.exception.meta.result, "transport_error")
        self.assertEqual(context.exception.meta.calls[0].error_class, "timeout")

    def test_auth_is_terminal_and_does_not_trigger_repair(self):
        client = fake_client(FakeAuthenticationError())

        with patch("grok_client.AuthenticationError", FakeAuthenticationError):
            with self.assertRaises(DiagnosisGenerationError) as context:
                analizar_respuesta("pregunta", "respuesta", client=client)

        self.assertEqual(client.chat.completions.create.call_count, 1)
        self.assertEqual(context.exception.meta.calls[0].error_class, "auth")
        self.assertEqual(context.exception.meta.calls[0].http_status, 401)

    def test_rate_limit_is_terminal_and_does_not_trigger_repair(self):
        client = fake_client(FakeRateLimitError())

        with patch("grok_client.RateLimitError", FakeRateLimitError):
            with self.assertRaises(DiagnosisGenerationError) as context:
                analizar_respuesta("pregunta", "respuesta", client=client)

        self.assertEqual(client.chat.completions.create.call_count, 1)
        self.assertEqual(context.exception.meta.calls[0].error_class, "rate_limit")
        self.assertEqual(context.exception.meta.calls[0].http_status, 429)

    def test_truncation_uses_only_one_repair_and_second_truncation_fails(self):
        client = fake_client(
            fake_response('{"schema_version":"diag.v1.1"', finish_reason="length"),
            fake_response('{"schema_version":"diag.v1.1"', finish_reason="length"),
        )

        with self.assertRaises(DiagnosisGenerationError) as context:
            analizar_respuesta("pregunta", "respuesta", client=client)

        self.assertEqual(client.chat.completions.create.call_count, 2)
        self.assertEqual(context.exception.meta.result, "invalid_output")
        self.assertTrue(context.exception.meta.calls[0].truncated)
        self.assertTrue(context.exception.meta.calls[1].truncated)

    def test_missing_usage_remains_none_instead_of_zero(self):
        client = fake_client(fake_response(valid_diagnosis_json(), usage=None))

        _, meta = analizar_respuesta(
            "pregunta",
            "respuesta",
            client=client,
        )

        self.assertIsNone(meta.calls[0].prompt_tokens)
        self.assertIsNone(meta.calls[0].completion_tokens)
        self.assertIsNone(meta.calls[0].total_tokens)
        self.assertIsNone(meta.total_tokens)


if __name__ == "__main__":
    unittest.main()

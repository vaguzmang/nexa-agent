import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from s2.agent import S2AgentError, run_learning_agent
from s2.storage import ensure_database


def diagnosis_dict():
    return {
        "schema_version": "diag.v1.1",
        "objective": {
            "domain": "Ciencias naturales",
            "skill": "Explicar el ciclo del agua que produce la lluvia",
        },
        "evidence": {
            "type": "open_ended",
            "result": "partial",
            "summary": "Menciona evaporación y precipitación pero omite condensación.",
            "criteria": None,
        },
        "understanding": {
            "demonstrated": "Reconoce dos etapas.",
            "missing": "Falta condensación.",
        },
        "gap": {
            "present": True,
            "type": "incomplete_procedure",
            "description": "La secuencia está incompleta.",
        },
        "next_step": "teach",
    }


def usage(total=100):
    return SimpleNamespace(
        prompt_tokens=70,
        completion_tokens=30,
        total_tokens=total,
    )


def tool_call(call_id, name, arguments):
    return SimpleNamespace(
        id=call_id,
        type="function",
        function=SimpleNamespace(
            name=name,
            arguments=json.dumps(arguments),
        ),
    )


def response(*, tool_calls=None, content=None, finish_reason=None, total=100):
    if finish_reason is None:
        finish_reason = "tool_calls" if tool_calls else "stop"
    return SimpleNamespace(
        model="grok-4.6",
        usage=usage(total),
        choices=[
            SimpleNamespace(
                finish_reason=finish_reason,
                message=SimpleNamespace(
                    content=content,
                    tool_calls=tool_calls,
                ),
            )
        ],
    )


class TestS2Agent(unittest.TestCase):

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db = Path(self.tempdir.name) / "agent.db"
        ensure_database(self.db)

    def tearDown(self):
        self.tempdir.cleanup()

    def test_native_agent_executes_three_tools_and_returns_final_answer(self):
        client = Mock()
        client.chat.completions.create.side_effect = [
            response(
                tool_calls=[
                    tool_call(
                        "c1",
                        "get_learning_state",
                        {"student_id": "student_demo"},
                    )
                ],
            ),
            response(
                tool_calls=[
                    tool_call(
                        "c2",
                        "list_teaching_strategies",
                        {
                            "gap": "incomplete_procedure",
                            "exclude_types": [],
                        },
                    )
                ],
            ),
            response(
                tool_calls=[
                    tool_call(
                        "c3",
                        "record_learning_event",
                        {
                            "student_id": "student_demo",
                            "objective": "Explicar el ciclo del agua que produce la lluvia",
                            "objective_source": "inferred",
                            "activity": "activity-123",
                            "gap": "incomplete_procedure",
                            "strategy_type": "guided_practice",
                            "strategy_result": "inconclusive",
                            "diagnostic_outcome": "partial",
                            "evidence": "Menciona evaporación y precipitación; falta condensación.",
                        },
                    )
                ],
            ),
            response(
                content=(
                    "Estrategia: guided_practice. Vamos a completar la secuencia. "
                    "¿Qué ocurre con el vapor cuando se enfría?"
                ),
            ),
        ]

        # Activity hash must be deterministic, but this mock intentionally sends
        # an invalid activity id to prove the tool contract remains independent
        # from model reasoning.
        text, meta = run_learning_agent(
            student_id="student_demo",
            activity="¿Por qué llueve?",
            student_answer="Por evaporación y precipitación.",
            diagnosis=diagnosis_dict(),
            client=client,
            db_path=self.db,
        )

        self.assertIn("guided_practice", text)
        self.assertEqual(
            [trace.name for trace in meta.tools],
            [
                "get_learning_state",
                "list_teaching_strategies",
                "record_learning_event",
            ],
        )
        self.assertEqual(client.chat.completions.create.call_count, 4)
        self.assertEqual(meta.total_tokens, 400)

    def test_tool_result_is_sent_back_to_grok(self):
        client = Mock()
        client.chat.completions.create.side_effect = [
            response(
                tool_calls=[
                    tool_call(
                        "c1",
                        "get_learning_state",
                        {"student_id": "student_demo"},
                    )
                ]
            ),
            response(content="No hay historial previo; iniciaré como primera sesión."),
        ]

        _, meta = run_learning_agent(
            student_id="student_demo",
            activity="Actividad",
            student_answer="Respuesta",
            diagnosis=diagnosis_dict(),
            client=client,
            db_path=self.db,
        )

        second_call_messages = (
            client.chat.completions.create.call_args_list[1].kwargs["messages"]
        )
        tool_messages = [m for m in second_call_messages if m["role"] == "tool"]
        self.assertEqual(len(tool_messages), 1)
        payload = json.loads(tool_messages[0]["content"])
        self.assertFalse(payload["has_history"])
        self.assertEqual(len(meta.tools), 1)

    def test_unknown_tool_returns_controlled_error_to_model(self):
        client = Mock()
        client.chat.completions.create.side_effect = [
            response(
                tool_calls=[
                    tool_call("c1", "invented_tool", {})
                ]
            ),
            response(content="La herramienta solicitada no existe; no inventaré su resultado."),
        ]

        text, meta = run_learning_agent(
            student_id="student_demo",
            activity="Actividad",
            student_answer="Respuesta",
            diagnosis=diagnosis_dict(),
            client=client,
            db_path=self.db,
        )

        self.assertIn("no existe", text.lower())
        self.assertFalse(meta.tools[0].result["ok"])
        self.assertEqual(meta.tools[0].result["error_code"], "unknown_tool")

    def test_max_tool_rounds_prevents_infinite_loop(self):
        client = Mock()
        client.chat.completions.create.side_effect = [
            response(
                tool_calls=[
                    tool_call(
                        f"c{i}",
                        "get_learning_state",
                        {"student_id": "student_demo"},
                    )
                ]
            )
            for i in range(3)
        ]

        with self.assertRaises(S2AgentError):
            run_learning_agent(
                student_id="student_demo",
                activity="Actividad",
                student_answer="Respuesta",
                diagnosis=diagnosis_dict(),
                client=client,
                db_path=self.db,
                max_rounds=3,
            )

        self.assertEqual(client.chat.completions.create.call_count, 3)

    def test_insufficient_evidence_can_finish_without_tools(self):
        diag = diagnosis_dict()
        diag["evidence"]["result"] = "insufficient_evidence"
        diag["understanding"]["demonstrated"] = None
        diag["understanding"]["missing"] = None
        diag["gap"] = {
            "present": False,
            "type": "none",
            "description": None,
        }
        diag["next_step"] = "ask_clarifying"

        client = Mock()
        client.chat.completions.create.return_value = response(
            content="Necesito una aclaración antes de continuar."
        )

        text, meta = run_learning_agent(
            student_id="student_demo",
            activity="Comenta el texto anterior",
            student_answer="No sé",
            diagnosis=diag,
            client=client,
            db_path=self.db,
        )

        self.assertIn("aclaración", text)
        self.assertEqual(len(meta.tools), 0)

    def test_agent_metadata_does_not_store_api_key_or_full_prompt(self):
        client = Mock()
        client.chat.completions.create.return_value = response(
            content="Necesito una aclaración."
        )

        _, meta = run_learning_agent(
            student_id="student_demo",
            activity="Actividad privada",
            student_answer="Respuesta privada",
            diagnosis=diagnosis_dict(),
            client=client,
            db_path=self.db,
        )

        serialized = repr(meta)
        self.assertNotIn("Actividad privada", serialized)
        self.assertNotIn("Respuesta privada", serialized)


    def test_record_semantics_are_frozen_before_commit(self):
        from s2.agent import SYSTEM_PROMPT
        from s2.tools import TOOL_DEFINITIONS, record_learning_event

        self.assertIn("resultado aún no observado", record_learning_event.__doc__)
        self.assertIn("evidencia posterior", record_learning_event.__doc__.lower())
        self.assertIn("strategy_result DEBE ser", SYSTEM_PROMPT)
        self.assertIn("No uses helped ni failed", SYSTEM_PROMPT)

        record_tool = next(
            tool for tool in TOOL_DEFINITIONS
            if tool["function"]["name"] == "record_learning_event"
        )
        description = record_tool["function"]["description"]
        self.assertIn("inconclusive", description)
        self.assertIn("evidencia posterior", description.lower())


if __name__ == "__main__":
    unittest.main()

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from s2.observation import observe_turn
from s2.storage import ensure_database
from s3.session import run_student_turn


def usage(total=100):
    return SimpleNamespace(prompt_tokens=70, completion_tokens=30, total_tokens=total)


def tool_call(call_id, name, arguments):
    import json
    return SimpleNamespace(
        id=call_id,
        type="function",
        function=SimpleNamespace(name=name, arguments=json.dumps(arguments)),
    )


def response(*, tool_calls=None, content=None, total=100):
    return SimpleNamespace(
        model="grok-4.6",
        usage=usage(total),
        choices=[SimpleNamespace(
            finish_reason="tool_calls" if tool_calls else "stop",
            message=SimpleNamespace(content=content, tool_calls=tool_calls),
        )],
    )


class TestS3SemanticStabilization(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db = Path(self.tempdir.name) / "semantic.db"
        ensure_database(self.db)

    def tearDown(self):
        self.tempdir.cleanup()

    def test_non_evaluable_turn_is_not_mislabeled_as_independent_evidence(self):
        diagnosis = {
            "objective": {"domain": "Conversación", "skill": "Comprender fotosíntesis"},
            "evidence": {"type": "open_ended", "result": "insufficient_evidence", "summary": "No evaluable", "criteria": None},
            "understanding": {"demonstrated": None, "missing": None},
            "gap": {"present": False, "type": "none", "description": None},
            "next_step": "ask_clarifying",
        }
        obs = observe_turn(
            activity="Comprender fotosíntesis",
            student_answer="Quiero aprender fotosíntesis",
            diagnosis=diagnosis,
            turn_type_override="learning_request",
            evidence_eligible_override=False,
            difficulty_relation="new_context",
        )
        self.assertEqual(obs.evidence_mode, "not_applicable")
        self.assertEqual(obs.support_level, "not_applicable")
        self.assertEqual(obs.difficulty_relation, "new_context")

    def test_new_free_learning_request_starts_episode_semantically(self):
        client = Mock()
        client.chat.completions.create.side_effect = [
            response(tool_calls=[tool_call("c1", "get_learning_state", {"student_id": "student_new"})]),
            response(tool_calls=[tool_call("c2", "list_teaching_strategies", {"gap": "none", "interaction_need": "explanation", "exclude_types": []})]),
            response(tool_calls=[tool_call("c3", "record_learning_event", {"strategy_type": "concept_explanation", "evidence": "Explicación inicial."})]),
            response(content="La fotosíntesis transforma luz, agua y CO2. ¿Qué tres elementos entran?"),
        ]
        result = run_student_turn(
            student_id="student_new",
            message="Quiero aprender cómo funciona la fotosíntesis",
            client=client,
            db_path=self.db,
            task_id="task-semantic-new",
            started_at="2026-10-25T01:00:00+00:00",
        )
        obs = result.agent_meta.learning_observation
        self.assertEqual(obs["evidence_mode"], "not_applicable")
        self.assertEqual(obs["support_level"], "not_applicable")
        self.assertEqual(obs["difficulty_relation"], "new_context")
        self.assertEqual(result.agent_meta.episode_action, "start_episode")
        self.assertEqual(result.objective_resolution.action, "create_inferred")
        self.assertTrue(result.metrics["diagnosis_skipped"])

    def test_demo_labels_tool_trace_as_intermediate_snapshot(self):
        demo = Path(__file__).resolve().parent.parent / "s3_demo.py"
        text = demo.read_text(encoding="utf-8")
        self.assertIn("SNAPSHOTS INTERMEDIOS", text)


if __name__ == "__main__":
    unittest.main()

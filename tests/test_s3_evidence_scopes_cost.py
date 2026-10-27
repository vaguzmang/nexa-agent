import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from s2.agent import COMPACT_LIST_TOOL, COMPACT_RECORD_TOOL, SYSTEM_PROMPT, SYSTEM_PROMPT_COMPACT, run_learning_agent
from s2.observation import observe_turn
from s2.storage import ensure_database
from s2.tools import list_teaching_strategies, record_learning_event
from s3.effectiveness import build_population_analytics_payload, build_strategy_effectiveness_profile
from s3.pedagogy import plan_strategy_candidates


class TestEvidenceScopesAndCost(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db = Path(self.tempdir.name) / "nexa.db"
        ensure_database(self.db)

    def tearDown(self):
        self.tempdir.cleanup()

    def _apply_close(self, student, strategy, *, institution, subject, objective_family, helped=True, independent=True):
        ap = record_learning_event(
            student_id=student, objective="Objetivo", objective_source="inferred",
            activity=f"a-{student}-{strategy}", gap="none", strategy_type=strategy,
            strategy_result="inconclusive", diagnostic_outcome="partial", evidence="inicio",
            event_type="strategy_applied", objective_id="obj", episode_id=f"ep-{student}",
            turn_type="attempt", task_type="conceptual", response_format="open",
            evidence_mode="independent", independent_evidence_eligible=True,
            support_level="none", intervention_support_level="medium",
            institution_id=institution, subject_family=subject, objective_family=objective_family,
            db_path=self.db,
        )
        record_learning_event(
            student_id=student, objective="Objetivo", objective_source="inferred",
            activity=f"b-{student}-{strategy}", gap="none" if helped else "misconception",
            strategy_type=strategy, strategy_result="helped" if helped else "failed",
            diagnostic_outcome="correct" if helped else "incorrect", evidence="posterior",
            event_type="strategy_evaluated", objective_id="obj", evaluates_event_id=ap["event_id"],
            result_reason="objective_met" if helped else "same_error_persists", episode_id=f"ep-{student}",
            turn_type="attempt", task_type="conceptual", response_format="open",
            evidence_mode="independent" if independent else "guided",
            independent_evidence_eligible=bool(independent), support_level="none" if independent else "medium",
            db_path=self.db,
        )
        return ap

    def test_population_payload_has_no_student_identity(self):
        payload = build_population_analytics_payload(
            geography_level="municipality", geography_key="m-001",
            subject_family="math", objective_family="fractions",
            learners_count=120, difficulty_count=47, period="2026-Q4",
        )
        self.assertNotIn("student_id", payload)
        self.assertEqual(payload["scope"], "population")

    def test_population_evidence_never_changes_individual_ranking(self):
        for i in range(8):
            self._apply_close(f"other-{i}", "analogy", institution=f"school-{i}", subject="science", objective_family="water")
        plan = plan_strategy_candidates(
            eligible=[{"type":"analogy","summary":"a"},{"type":"concept_explanation","summary":"c"}],
            student_id="target", task_type="conceptual", db_path=self.db,
        )
        self.assertEqual(plan[0]["priority_score"], plan[1]["priority_score"])

    def test_institutional_evidence_does_not_cross_institutions(self):
        for i in range(6):
            self._apply_close(f"a-{i}", "concept_explanation", institution="school-A", subject="science", objective_family="water")
        profile = build_strategy_effectiveness_profile(
            student_id="new", task_type="conceptual", institution_id="school-B",
            subject_family="science", objective_family="water", db_path=self.db,
        )
        self.assertEqual(profile["institutional"], {})

    def test_guided_outcome_does_not_feed_institutional_profile(self):
        for i in range(6):
            self._apply_close(f"g-{i}", "concept_explanation", institution="school-A", subject="science", objective_family="water", independent=False)
        profile = build_strategy_effectiveness_profile(
            student_id="new", task_type="conceptual", institution_id="school-A",
            subject_family="science", objective_family="water", db_path=self.db,
        )
        self.assertEqual(profile["institutional"], {})

    def test_repeated_events_from_one_student_count_once_institutionally(self):
        for j in range(3):
            self._apply_close("same-student", "concept_explanation", institution="school-A", subject="science", objective_family="water")
        profile = build_strategy_effectiveness_profile(
            student_id="new", task_type="conceptual", institution_id="school-A",
            subject_family="science", objective_family="water", db_path=self.db,
        )
        entry = profile["institutional"]["concept_explanation"]
        self.assertEqual(entry["unique_students"], 1)

    def test_task_axes_separate_task_type_and_response_format(self):
        diag = {"evidence":{"type":"closed_ended","result":"insufficient_evidence","summary":"x","criteria":None},"gap":{"present":False,"type":"none","description":None}}
        obs = observe_turn(
            activity="Resuelve 2(x+3)=10 y explica por qué funciona",
            student_answer="Quiero aprender paso a paso",
            diagnosis=diag, turn_type_override="learning_request",
        )
        self.assertEqual(obs.task_type, "mixed")
        self.assertEqual(obs.response_format, "closed")

    def test_compact_tool_schemas_are_materially_smaller(self):
        from s2.tools import TOOL_DEFINITIONS
        full = len(json.dumps(TOOL_DEFINITIONS, ensure_ascii=False))
        compact = len(json.dumps([COMPACT_LIST_TOOL, COMPACT_RECORD_TOOL], ensure_ascii=False))
        self.assertLess(compact, full * 0.45)
        self.assertLess(len(SYSTEM_PROMPT_COMPACT), len(SYSTEM_PROMPT) * 0.55)

    def test_compact_mode_skips_duplicate_state_tool_and_uses_two_tools(self):
        def tc(cid,name,args):
            return SimpleNamespace(id=cid,type="function",function=SimpleNamespace(name=name,arguments=json.dumps(args)))
        def resp(tool_calls=None,content=None):
            return SimpleNamespace(model="grok-4.6",usage=SimpleNamespace(prompt_tokens=10,completion_tokens=5,total_tokens=15),choices=[SimpleNamespace(finish_reason="tool_calls" if tool_calls else "stop",message=SimpleNamespace(content=content,tool_calls=tool_calls))])
        client=Mock()
        client.chat.completions.create.side_effect=[
            resp([tc("c1","list_teaching_strategies",{})]),
            resp([tc("c2","record_learning_event",{"strategy_type":"worked_example","evidence":"ejemplo"})]),
            resp(content="Vamos paso a paso. ¿Cuál sería el primer paso?"),
        ]
        diagnosis={
            "schema_version":"diag.v1.1","objective":{"domain":"math","skill":"Resolver ecuaciones"},
            "evidence":{"type":"open_ended","result":"insufficient_evidence","summary":"inicio","criteria":None},
            "understanding":{"demonstrated":None,"missing":None},"gap":{"present":False,"type":"none","description":None},"next_step":"ask_clarifying",
        }
        state={"has_history":False,"current_objective":None,"current_objective_id":None,"objective_source":None,"strategies_tried":[],"previous_confirmed_evidence":[],"component_progress":[]}
        text, meta = run_learning_agent(
            student_id="s", activity="Resolver ecuaciones", student_answer="Quiero aprender a resolver 2(x+3)=10",
            diagnosis=diagnosis, objective_id="obj", objective_source="inferred",
            turn_type_override="learning_request", interaction_need_override="explanation", objective_action="create_inferred",
            cost_optimized=True, preloaded_state=state, client=client, db_path=self.db,
        )
        self.assertIn("paso", text.lower())
        self.assertEqual([t.name for t in meta.tools], ["list_teaching_strategies","record_learning_event"])
        self.assertTrue(meta.cost_optimized)

if __name__ == "__main__":
    unittest.main()

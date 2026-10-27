import os
import tempfile
import unittest
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from s2.storage import connect, ensure_database
from s3.metrics import build_task_metrics, persist_task_metrics


@dataclass(frozen=True)
class DiagCall:
    kind: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class TestS3Metrics(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db = Path(self.tempdir.name) / "metrics.db"
        ensure_database(self.db)

    def tearDown(self):
        self.tempdir.cleanup()

    def _meta(self):
        diagnosis_meta = SimpleNamespace(
            calls=(DiagCall("primary", 100, 20, 120), DiagCall("repair", 50, 10, 60)),
            total_tokens=180,
            total_latency_ms=1200,
        )
        agent_meta = SimpleNamespace(
            calls=(SimpleNamespace(prompt_tokens=200, completion_tokens=40, total_tokens=240),),
            tools=(object(), object()),
            total_tokens=240,
            total_latency_ms=1800,
        )
        return diagnosis_meta, agent_meta

    def test_end_to_end_metrics_sum_diagnosis_and_agent(self):
        d, a = self._meta()
        metrics = build_task_metrics(task_id="t1", diagnosis_meta=d, agent_meta=a)
        self.assertEqual(metrics["total_tokens"], 420)
        self.assertEqual(metrics["total_latency_ms"], 3000)
        self.assertEqual(metrics["llm_calls"], 3)
        self.assertEqual(metrics["tool_calls"], 2)
        self.assertEqual(metrics["repairs"], 1)

    def test_cost_is_only_estimated_when_rates_are_configured(self):
        d, a = self._meta()
        with patch.dict(os.environ, {
            "GROK_INPUT_USD_PER_MILLION": "2",
            "GROK_OUTPUT_USD_PER_MILLION": "4",
        }, clear=False):
            metrics = build_task_metrics(task_id="t2", diagnosis_meta=d, agent_meta=a)
        expected = (350 * 2 + 70 * 4) / 1_000_000
        self.assertAlmostEqual(metrics["estimated_cost_usd"], expected)

    def test_task_metrics_persistence_is_idempotent_by_task_id(self):
        d, a = self._meta()
        metrics = build_task_metrics(task_id="t3", diagnosis_meta=d, agent_meta=a, status="success")
        persist_task_metrics(metrics, db_path=self.db)
        metrics["status"] = "rechecked"
        persist_task_metrics(metrics, db_path=self.db)
        with closing(connect(self.db)) as connection:
            row = connection.execute("SELECT COUNT(*), status FROM task_runs WHERE task_id='t3'").fetchone()
        self.assertEqual(row[0], 1)
        self.assertEqual(row[1], "rechecked")


if __name__ == "__main__":
    unittest.main()

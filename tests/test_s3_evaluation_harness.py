import os
from contextlib import closing
import sqlite3
import tempfile
import unittest

from s2.storage import ensure_database
from s3.evaluation import (
    evaluation_report,
    latest_task_id,
    upsert_evaluation,
)


class S3EvaluationHarnessTests(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        ensure_database(self.db_path)

    def tearDown(self):
        try:
            os.remove(self.db_path)
        except FileNotFoundError:
            pass

    def _task(self, task_id="task-test", *, optimized=1, tokens=1000, flow_status="success"):
        with closing(sqlite3.connect(self.db_path)) as c:
            c.execute(
                """
                INSERT INTO task_runs(
                    task_id, started_at, finished_at, total_tokens, visible_token_sum,
                    total_latency_ms, llm_calls, tool_calls, repairs, errors,
                    status, diagnosis_skipped, cost_optimized
                ) VALUES (?, '2026-01-01', '2026-01-01', ?, ?, 100, 2, 1, 0, 0, ?, 1, ?)
                """,
                (task_id, tokens, tokens - 100, flow_status, optimized),
            )
            c.commit()

    def test_latest_task_uses_latest_optimized_success(self):
        self._task("old", optimized=0)
        self._task("new", optimized=1)
        self.assertEqual(latest_task_id(db_path=self.db_path), "new")

    def test_valid_case_is_included(self):
        self._task()
        upsert_evaluation(
            task_id="task-test", benchmark_case_id="B1", benchmark_status="valid",
            flow_type="learning_request", quality_pass=True, db_path=self.db_path,
        )
        report = evaluation_report(db_path=self.db_path)
        self.assertEqual(report["valid_benchmark"]["tasks"], 1)
        self.assertEqual(report["valid_benchmark"]["quality_success_rate"], 1.0)

    def test_invalid_case_is_excluded_from_main_benchmark(self):
        self._task()
        upsert_evaluation(
            task_id="task-test", benchmark_case_id="B1", benchmark_status="invalid",
            flow_type="other", quality_pass=False, db_path=self.db_path,
        )
        report = evaluation_report(db_path=self.db_path)
        self.assertEqual(report["valid_benchmark"]["tasks"], 0)
        self.assertEqual(report["marked_invalid"], 1)

    def test_unmarked_task_is_excluded(self):
        self._task()
        report = evaluation_report(db_path=self.db_path)
        self.assertEqual(report["valid_benchmark"]["tasks"], 0)

    def test_report_groups_by_flow(self):
        self._task("t1", tokens=1000)
        self._task("t2", tokens=2000)
        upsert_evaluation(
            task_id="t1", benchmark_case_id="B1", benchmark_status="valid",
            flow_type="learning_request", quality_pass=True, db_path=self.db_path,
        )
        upsert_evaluation(
            task_id="t2", benchmark_case_id="B2", benchmark_status="valid",
            flow_type="diagnosis_required", quality_pass=True, db_path=self.db_path,
        )
        report = evaluation_report(db_path=self.db_path)
        self.assertEqual(report["by_flow"]["learning_request"]["tasks"], 1)
        self.assertEqual(report["by_flow"]["diagnosis_required"]["tasks"], 1)

    def test_baseline_remains_separate(self):
        self._task("legacy", optimized=0, tokens=3000)
        self._task("optimized", optimized=1, tokens=1000)
        upsert_evaluation(
            task_id="optimized", benchmark_case_id="B1", benchmark_status="valid",
            flow_type="learning_request", quality_pass=True, db_path=self.db_path,
        )
        report = evaluation_report(db_path=self.db_path)
        self.assertEqual(report["legacy_or_baseline"]["tasks"], 1)
        self.assertEqual(report["legacy_or_baseline"]["reported_tokens"]["avg"], 3000.0)


if __name__ == "__main__":
    unittest.main()

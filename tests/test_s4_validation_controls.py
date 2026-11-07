import unittest
from pathlib import Path

class S4ValidationControlsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root=Path(__file__).resolve().parents[1]

    def test_stage_scripts_exist(self):
        for name in ("s4_test_20.ps1","s4_test_100.ps1","s4_test_1h.ps1","s4_official_12h.ps1"):
            self.assertTrue((self.root/name).exists(),name)

    def test_official_target_exceeds_one_thousand(self):
        text=(self.root/"s4_official_12h.ps1").read_text(encoding="utf-8")
        self.assertIn("-TargetCompleted 1100",text)
        self.assertIn("-DurationHours 12.25",text)

    def test_one_hour_stage_is_explicitly_unattended(self):
        text=(self.root/"s4_test_1h.ps1").read_text(encoding="utf-8")
        self.assertIn("--duration-hours 1.05",text)
        self.assertIn("--target-completed 90",text)

    def test_runner_reuses_persisted_min_end(self):
        text=(self.root/"s4_load_runner.py").read_text(encoding="utf-8")
        self.assertIn('persisted_run=get_run',text)
        self.assertIn('persisted_run["min_end_at"]',text)

if __name__=="__main__":
    unittest.main()

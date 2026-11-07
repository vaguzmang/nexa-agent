import json,unittest
from pathlib import Path

class IcfesInputQualityAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root=Path(__file__).resolve().parents[1]
        cls.audit=json.loads((root/"data"/"S3_ICFES_INPUT_QUALITY_AUDIT_V1.json").read_text(encoding="utf-8"))
    def test_three_original_cases_are_flagged_as_input_invalid(self):
        self.assertEqual({x["case_id"] for x in self.audit["invalid_input_cases"]},{"ICFES-07","ICFES-12","ICFES-13"})
    def test_three_replacements_are_distinct_and_auditable(self):
        reps=self.audit["replacement_questions"]
        self.assertEqual(len(reps),3)
        self.assertEqual(len({x["case_id"] for x in reps}),3)
        self.assertEqual({x["question"] for x in reps},{25,34,36})
    def test_replacement_keys_are_present(self):
        for x in self.audit["replacement_questions"]:
            self.assertIn(x["official_answer"],{"A","B","C","D"})
            self.assertIn(x["response_mode"],{"correct","incorrect"})
if __name__=="__main__": unittest.main()

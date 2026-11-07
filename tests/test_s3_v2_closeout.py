import json, unittest
from pathlib import Path

class S3V2CloseoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root=Path(__file__).resolve().parents[1]
        cls.data=json.loads((root/"artifacts"/"S3_REAL_DOMAIN_V2_SUMMARY.json").read_text(encoding="utf-8"))

    def test_real_domain_target_is_30(self):
        self.assertEqual(self.data["domain_data"]["target_scenarios"],30)

    def test_final_integral_success_is_29_of_30(self):
        r=self.data["remediation"]
        self.assertEqual(r["final_validated_pass_scenarios"],29)
        self.assertEqual(r["final_unresolved_technical_scenarios"],1)

    def test_gateway_initial_real_cost_is_preserved(self):
        g=self.data["gateway_cost"]["initial_increment"]
        self.assertEqual(g["requests"],152)
        self.assertAlmostEqual(g["cost_usd"],1.59,places=6)

    def test_full_closeout_cost_is_preserved(self):
        g=self.data["gateway_cost"]["full_s3_v2_spend"]
        self.assertEqual(g["requests"],169)
        self.assertAlmostEqual(g["cost_usd"],1.76,places=6)

if __name__=="__main__": unittest.main()

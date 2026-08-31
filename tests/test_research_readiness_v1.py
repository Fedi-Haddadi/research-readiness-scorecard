import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agents.skills.research_readiness_v1 import assemble_research_readiness_scorecard_v1
from agents.agent import run_research_readiness_agent


class ResearchReadinessV1Tests(unittest.TestCase):
    def test_critical_sample_size_forces_no_go(self):
        scorecard = assemble_research_readiness_scorecard_v1(
            section_map={
                "title": True,
                "abstract": True,
                "introduction": True,
                "methods": True,
                "results": True,
                "discussion": True,
                "references": True,
            },
            claims=[{"claim_type": "sample_size", "text_span": "n=142", "value": "142"}],
            table_values=[{"value": "148", "raw_span": "n=148"}],
            table_notes=[{"text": "p-value not reported", "contains_p_value": False}],
            consistency_issues=[
                {
                    "issue_type": "number_mismatch",
                    "severity": "critical",
                    "explanation": "Sample size mismatch: draft n=142 vs table n=148",
                    "suggested_fix": "Align n",
                }
            ],
            references=[{"doi": "10.1/x", "cited": True, "year_match": True, "year": 2020, "status": "ok"}],
            meeting_actions=[],
            ethics_compliance={"status": "not_assessed"},
        )
        self.assertEqual(scorecard["readiness"], "no-go")
        # One critical penalty (0.25) → score 75; band still forced no-go by critical-issue floor
        self.assertLessEqual(scorecard["dimensions"]["claim_evidence_integrity"]["score"], 75)
        self.assertTrue(
            any("critical" in n.lower() for n in scorecard["band_floors"]["applied_notes"])
        )
        self.assertEqual(scorecard["scorecard_version"], "v1")

    def test_fixture_package_runs(self):
        package = ROOT / "fixtures" / "sample_package"
        result = run_research_readiness_agent(package, run_ethics_llm=True)
        sc = result["scorecard"]
        self.assertIn(sc["readiness"], {"go", "caution", "no-go"})
        self.assertTrue(Path(result["scorecard_path"]).exists())
        self.assertTrue(Path(result["ethics_path"]).exists())
        # Planted critical n mismatch should keep this from being a clean go
        self.assertNotEqual(sc["readiness"], "go")


if __name__ == "__main__":
    unittest.main()

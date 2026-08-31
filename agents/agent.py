"""Research Readiness agent — orchestrates skills and writes scorecard artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from agents.llm.client import LLMClient, get_default_client
from agents.skills.ethics_compliance import classify_ethics_compliance
from agents.skills.llm_assessments import assess_package_with_llm, merge_claim_issues
from agents.skills.research_readiness_v1 import assemble_research_readiness_scorecard_v1


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def run_research_readiness_agent(
    package_dir: Path | str,
    *,
    output_dir: Optional[Path | str] = None,
    client: Optional[LLMClient] = None,
    run_ethics_llm: bool = True,
    run_llm_assessments: bool = True,
) -> dict[str, Any]:
    """Run the research readiness pipeline on a package directory."""
    package_dir = Path(package_dir)
    output_dir = Path(output_dir) if output_dir else package_dir / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)
    client = client or get_default_client()

    section_map = _load_json(package_dir / "section_map.json", {})
    claims = _load_json(package_dir / "claims.json", [])
    table_values = _load_json(package_dir / "table_values.json", [])
    table_notes = _load_json(package_dir / "table_notes.json", [])
    consistency_issues = _load_json(package_dir / "consistency_issues.json", [])
    references = _load_json(package_dir / "references.json", [])
    meeting_actions = _load_json(package_dir / "meeting_actions.json", [])
    draft = _read_text(package_dir / "draft.md")

    ethics_path = output_dir / "ethics_compliance.json"
    existing_ethics = package_dir / "ethics_compliance.json"
    if existing_ethics.exists() and not run_ethics_llm:
        ethics = _load_json(existing_ethics, {"status": "not_assessed"})
        ethics_path.write_text(json.dumps(ethics, indent=2), encoding="utf-8")
    else:
        ethics = classify_ethics_compliance(
            draft_text=draft,
            client=client,
            out_path=ethics_path,
        )

    assessments_path = output_dir / "llm_assessments.json"
    if run_llm_assessments:
        llm_assessments = assess_package_with_llm(
            draft_text=draft,
            references=references,
            claims=claims,
            table_values=table_values,
            table_notes=table_notes,
            consistency_issues=consistency_issues,
            section_map=section_map,
            client=client,
            out_path=assessments_path,
        )
        consistency_issues = merge_claim_issues(
            consistency_issues,
            llm_assessments.get("claim_evidence_issues") or [],
        )
    else:
        llm_assessments = {"source": "skipped"}
        assessments_path.write_text(json.dumps(llm_assessments, indent=2), encoding="utf-8")

    scorecard = assemble_research_readiness_scorecard_v1(
        section_map=section_map,
        claims=claims,
        table_values=table_values,
        table_notes=table_notes,
        consistency_issues=consistency_issues,
        references=references,
        meeting_actions=meeting_actions,
        ethics_compliance=ethics,
        llm_assessments=llm_assessments,
    )

    out_scorecard = output_dir / "research_readiness_scorecard_v1.json"
    out_scorecard.write_text(json.dumps(scorecard, indent=2), encoding="utf-8")

    return {
        "scorecard_path": str(out_scorecard),
        "ethics_path": str(ethics_path),
        "assessments_path": str(assessments_path),
        "scorecard": scorecard,
    }


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Research Readiness Scorecard agent")
    parser.add_argument(
        "--package",
        default="fixtures/sample_package",
        help="Path to research package artifacts directory",
    )
    parser.add_argument("--output", default=None, help="Output directory (default: <package>/outputs)")
    parser.add_argument(
        "--skip-ethics-llm",
        action="store_true",
        help="Reuse package ethics_compliance.json if present",
    )
    parser.add_argument(
        "--skip-llm-assessments",
        action="store_true",
        help="Skip LLM citation/stats/consistency review (heuristics only)",
    )
    args = parser.parse_args()

    result = run_research_readiness_agent(
        args.package,
        output_dir=args.output,
        run_ethics_llm=not args.skip_ethics_llm,
        run_llm_assessments=not args.skip_llm_assessments,
    )
    sc = result["scorecard"]
    print(f"overall_score={sc['overall_score']} readiness={sc['readiness']}")
    print(f"wrote {result['scorecard_path']}")
    print(f"wrote {result['ethics_path']}")
    print(f"wrote {result['assessments_path']}")


if __name__ == "__main__":
    main()

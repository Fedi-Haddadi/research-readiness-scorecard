"""LLM-assisted assessments for dimensions that benefit from language understanding.

Used for citation quality, statistical reporting, narrative consistency, and
extra claim–evidence review. Falls back to deterministic heuristics when the
provider is placeholder or the model call fails.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from agents.llm.client import LLMClient, LLMMessage, get_default_client


def _write(path: Optional[Path], payload: dict[str, Any]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _heuristic_citation(references: list[dict[str, Any]]) -> dict[str, Any]:
    refs = references or []
    if not refs:
        return {
            "status": "assessed",
            "source": "heuristic",
            "doi_coverage": 0.0,
            "year_match_rate": 0.0,
            "cited_reference_coverage": 0.0,
            "orphan_ref_share": 0.0,
            "missing_critical_meta_count": 0,
            "issues": [{"type": "no_references", "detail": "No references provided"}],
            "notes": ["Heuristic fallback: empty reference list"],
            "confidence": 0.4,
        }
    n = len(refs)
    doi_ok = sum(1 for r in refs if r.get("doi") and str(r.get("doi")).lower() not in {"missing", "none", ""})
    comparable = [r for r in refs if "year_match" in r or "year_conflict" in str(r.get("status") or "").lower()]
    if comparable:
        year_match_rate = sum(
            1
            for r in comparable
            if r.get("year_match") is True or "conflict" not in str(r.get("status") or "").lower()
        ) / len(comparable)
    else:
        year_match_rate = 1.0
    cited = [r for r in refs if r.get("cited", True)]
    orphans = [r for r in refs if r.get("cited") is False]
    missing_meta = sum(
        1
        for r in refs
        if (not r.get("doi") or str(r.get("doi")).lower() in {"missing", "none", ""}) and not r.get("year")
    )
    issues = []
    for r in refs:
        if str(r.get("doi") or "").lower() in {"missing", "none", ""}:
            issues.append({"type": "missing_doi", "ref_id": r.get("id"), "detail": r.get("label") or r.get("id")})
        if r.get("year_match") is False or "conflict" in str(r.get("status") or "").lower():
            issues.append({"type": "year_conflict", "ref_id": r.get("id"), "detail": r.get("status")})
        if r.get("cited") is False:
            issues.append({"type": "orphan_reference", "ref_id": r.get("id"), "detail": r.get("label")})
    return {
        "status": "assessed",
        "source": "heuristic",
        "doi_coverage": doi_ok / n,
        "year_match_rate": year_match_rate,
        "cited_reference_coverage": len(cited) / n,
        "orphan_ref_share": len(orphans) / n,
        "missing_critical_meta_count": missing_meta,
        "issues": issues,
        "notes": ["Heuristic citation assessment (LLM unavailable or skipped)"],
        "confidence": 0.45,
    }


def _heuristic_statistics(
    *,
    draft_text: str,
    claims: list[dict[str, Any]],
    table_notes: list[dict[str, Any]],
    section_map: dict[str, Any],
) -> dict[str, Any]:
    blob = " ".join(
        [
            draft_text or "",
            *(str(c.get("text_span") or "") for c in claims or []),
            *(str(n.get("text") or "") for n in table_notes or []),
        ]
    ).lower()
    has_n = any(c.get("claim_type") == "sample_size" for c in claims or []) or "n=" in blob or "patients" in blob
    has_effect = any(c.get("claim_type") in {"or_ci", "difference", "rate", "mean"} for c in claims or []) or "or " in blob
    has_uncertainty = "95% ci" in blob or "confidence" in blob
    has_p = any(c.get("claim_type") == "p_value" for c in claims or []) or "p=" in blob or "p-value" in blob
    has_method = bool((section_map or {}).get("methods")) or "logistic regression" in blob or "methods" in blob
    p_missing = any(
        "p-value" in str(n.get("text") or "").lower() and "not reported" in str(n.get("text") or "").lower()
        for n in table_notes or []
    )
    return {
        "status": "assessed",
        "source": "heuristic",
        "has_sample_size": has_n,
        "has_effect": has_effect,
        "has_uncertainty": has_uncertainty,
        "has_p_or_bayesian": has_p,
        "has_methods_section": has_method,
        "p_asserted_but_table_missing": bool(has_p and p_missing),
        "notes": ["Heuristic statistical assessment (LLM unavailable or skipped)"],
        "confidence": 0.45,
    }


def _heuristic_narrative(consistency_issues: list[dict[str, Any]]) -> dict[str, Any]:
    dups = sum(1 for i in consistency_issues or [] if str(i.get("issue_type") or "").lower() == "duplication")
    contras = sum(
        1
        for i in consistency_issues or []
        if str(i.get("issue_type") or "").lower() in {"contradiction", "qualitative_contradiction"}
    )
    return {
        "status": "assessed",
        "source": "heuristic",
        "duplication_count": dups,
        "contradiction_count": contras,
        "findings": [
            {"type": i.get("issue_type"), "detail": i.get("explanation")}
            for i in consistency_issues or []
            if str(i.get("issue_type") or "").lower() in {"duplication", "contradiction", "qualitative_contradiction"}
        ],
        "notes": ["Heuristic narrative consistency from existing issues"],
        "confidence": 0.4,
    }


def assess_package_with_llm(
    *,
    draft_text: str,
    references: list[dict[str, Any]],
    claims: list[dict[str, Any]],
    table_values: list[dict[str, Any]],
    table_notes: list[dict[str, Any]],
    consistency_issues: list[dict[str, Any]],
    section_map: dict[str, Any],
    client: Optional[LLMClient] = None,
    out_path: Optional[Path] = None,
) -> dict[str, Any]:
    """Run LLM review for citations, stats, narrative consistency, and extra claim checks."""
    client = client or get_default_client()
    heuristic = {
        "citation": _heuristic_citation(references),
        "statistical_reporting": _heuristic_statistics(
            draft_text=draft_text,
            claims=claims,
            table_notes=table_notes,
            section_map=section_map,
        ),
        "narrative_consistency": _heuristic_narrative(consistency_issues),
        "claim_evidence_issues": [],
        "llm_provider": client.provider,
        "llm_model": client.model,
        "source": "heuristic",
    }

    if client.provider == "placeholder":
        heuristic["notes"] = ["placeholder provider: using heuristic assessments"]
        _write(out_path, heuristic)
        return heuristic

    system = (
        "You are a careful research manuscript auditor. Return JSON only. "
        "Never invent DOIs, years, p-values, or table numbers. "
        "If unsure, lower confidence and explain in notes."
    )
    user = f"""Audit this research package and return JSON with this shape:
{{
  "citation": {{
    "status": "assessed",
    "doi_coverage": 0.0-1.0,
    "year_match_rate": 0.0-1.0,
    "cited_reference_coverage": 0.0-1.0,
    "orphan_ref_share": 0.0-1.0,
    "missing_critical_meta_count": 0,
    "issues": [{{"type": "...", "ref_id": "...", "detail": "..."}}],
    "notes": ["..."],
    "confidence": 0.0-1.0
  }},
  "statistical_reporting": {{
    "status": "assessed",
    "has_sample_size": true,
    "has_effect": true,
    "has_uncertainty": true,
    "has_p_or_bayesian": true,
    "has_methods_section": true,
    "p_asserted_but_table_missing": false,
    "notes": ["..."],
    "confidence": 0.0-1.0
  }},
  "narrative_consistency": {{
    "status": "assessed",
    "duplication_count": 0,
    "contradiction_count": 0,
    "findings": [{{"type": "duplication|contradiction", "detail": "..."}}],
    "notes": ["..."],
    "confidence": 0.0-1.0
  }},
  "claim_evidence_issues": [
    {{
      "issue_type": "number_mismatch|unsupported_claim|citation_error|duplication",
      "severity": "critical|high|medium|low",
      "confidence": "high|medium|low",
      "draft_span": "...",
      "table_or_ref_span": "...",
      "explanation": "...",
      "suggested_fix": "..."
    }}
  ]
}}

Compare draft claims against tables. Flag only evidenced problems. Prefer quoting exact spans.

DRAFT:
{draft_text[:9000]}

REFERENCES_JSON:
{json.dumps(references, indent=2)[:4000]}

CLAIMS_JSON:
{json.dumps(claims, indent=2)[:3000]}

TABLE_VALUES_JSON:
{json.dumps(table_values, indent=2)[:3000]}

TABLE_NOTES_JSON:
{json.dumps(table_notes, indent=2)[:2000]}

EXISTING_ISSUES_JSON:
{json.dumps(consistency_issues, indent=2)[:3000]}

SECTION_MAP_JSON:
{json.dumps(section_map, indent=2)}
"""

    parsed, resp = client.complete_json(
        [LLMMessage("system", system), LLMMessage("user", user)],
        temperature=0.0,
        max_tokens=4096,
    )

    if not parsed:
        heuristic["notes"] = [resp.error or "LLM assessment failed; using heuristics"]
        heuristic["llm_provider"] = resp.provider
        heuristic["llm_model"] = resp.model
        _write(out_path, heuristic)
        return heuristic

    result = {
        "citation": {**heuristic["citation"], **(parsed.get("citation") or {}), "source": "llm"},
        "statistical_reporting": {
            **heuristic["statistical_reporting"],
            **(parsed.get("statistical_reporting") or {}),
            "source": "llm",
        },
        "narrative_consistency": {
            **heuristic["narrative_consistency"],
            **(parsed.get("narrative_consistency") or {}),
            "source": "llm",
        },
        "claim_evidence_issues": parsed.get("claim_evidence_issues") or [],
        "llm_provider": resp.provider,
        "llm_model": resp.model,
        "source": "llm",
        "notes": ["LLM package assessment"],
    }
    # Ensure nested status
    for key in ("citation", "statistical_reporting", "narrative_consistency"):
        result[key].setdefault("status", "assessed")
        result[key]["llm_provider"] = resp.provider
        result[key]["llm_model"] = resp.model

    _write(out_path, result)
    return result


def merge_claim_issues(
    existing: list[dict[str, Any]],
    llm_issues: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Merge LLM-found issues into existing list without obvious duplicates."""
    merged = list(existing or [])
    seen = {
        (
            str(i.get("issue_type") or "").lower(),
            str(i.get("explanation") or "").lower()[:160],
        )
        for i in merged
    }
    for issue in llm_issues or []:
        key = (
            str(issue.get("issue_type") or "").lower(),
            str(issue.get("explanation") or "").lower()[:160],
        )
        if key in seen:
            continue
        enriched = dict(issue)
        enriched.setdefault("source", "llm")
        merged.append(enriched)
        seen.add(key)
    return merged

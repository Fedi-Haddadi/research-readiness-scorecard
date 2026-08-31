"""Research Readiness Scorecard v1 — deterministic assembly from artifacts."""

from __future__ import annotations

from typing import Any, Optional

from agents.skills.ethics_compliance import ethics_dimension_score

SCORECARD_VERSION = "v1"

WEIGHTS = {
    "section_coverage": 0.10,
    "claim_evidence_integrity": 0.35,
    "statistical_reporting": 0.20,
    "citation_quality": 0.15,
    "internal_consistency": 0.15,
    "ethics_compliance": 0.05,
}

REQUIRED_SECTIONS = [
    "title",
    "abstract",
    "introduction",
    "methods",
    "results",
    "discussion",
    "references",
]
OPTIONAL_SECTIONS = ["limitations", "data_availability", "funding", "conflicts"]

BAND_RANK = {"go": 2, "caution": 1, "no-go": 0}


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def _score_from_rate(rate: float) -> int:
    return int(round(100 * _clamp(rate)))


def _band_from_score(score: int) -> str:
    if score >= 75:
        return "go"
    if score >= 50:
        return "caution"
    return "no-go"


def _stricter(a: str, b: str) -> str:
    return a if BAND_RANK[a] <= BAND_RANK[b] else b


def score_section_coverage(section_map: dict[str, Any]) -> dict[str, Any]:
    present = {str(k).lower(): bool(v) for k, v in (section_map or {}).items()}
    req_hit = sum(1 for s in REQUIRED_SECTIONS if present.get(s))
    opt_hit = sum(1 for s in OPTIONAL_SECTIONS if present.get(s))
    core_rate = req_hit / len(REQUIRED_SECTIONS)
    bonus = min(0.10, 0.025 * opt_hit)
    rate = _clamp(core_rate + bonus)
    missing = [s for s in REQUIRED_SECTIONS if not present.get(s)]
    return {
        "score": _score_from_rate(rate),
        "weight": WEIGHTS["section_coverage"],
        "status": "assessed",
        "metrics": {
            "required_present": req_hit,
            "required_total": len(REQUIRED_SECTIONS),
            "optional_present": opt_hit,
            "missing_required": missing,
            "rate": rate,
        },
        "notes": [f"Missing required sections: {missing}"] if missing else ["All required sections present."],
        "evidence": [],
    }


def score_claim_evidence(consistency_issues: list[dict[str, Any]], *, n_claims: int, n_table_values: int) -> dict[str, Any]:
    if n_claims <= 0 and n_table_values <= 0:
        return {
            "score": 0,
            "weight": WEIGHTS["claim_evidence_integrity"],
            "status": "assessed",
            "metrics": {"rate": 0.0, "reason": "no_claims_or_tables"},
            "notes": ["Cannot verify claim–evidence integrity without claims and table values."],
            "evidence": [],
        }

    pen_critical = 0.0
    pen_high = 0.0
    pen_medium = 0.0
    pen_low = 0.0
    critical_count = 0

    for issue in consistency_issues or []:
        severity = str(issue.get("severity") or _infer_severity(issue)).lower()
        itype = str(issue.get("issue_type") or "").lower()
        if severity == "critical" or (
            itype == "number_mismatch"
            and any(k in str(issue.get("explanation", "")).lower() for k in ("sample size", " n=", "primary"))
        ):
            # Treat primary n / endpoint mismatches as critical if marked or explained as such
            if severity == "critical" or "sample size" in str(issue.get("explanation", "")).lower():
                pen_critical += 0.25
                critical_count += 1
                continue
        if severity == "high":
            pen_high += 0.10
        elif severity == "medium":
            pen_medium += 0.05
        else:
            pen_low += 0.02

    pen_critical = min(0.50, pen_critical)
    pen_high = min(0.30, pen_high)
    pen_medium = min(0.15, pen_medium)
    pen_low = min(0.05, pen_low)
    rate = _clamp(1.0 - (pen_critical + pen_high + pen_medium + pen_low))

    return {
        "score": _score_from_rate(rate),
        "weight": WEIGHTS["claim_evidence_integrity"],
        "status": "assessed",
        "metrics": {
            "rate": rate,
            "penalties": {
                "critical": pen_critical,
                "high": pen_high,
                "medium": pen_medium,
                "low": pen_low,
            },
            "critical_count": critical_count,
            "issue_count": len(consistency_issues or []),
            "n_claims": n_claims,
            "n_table_values": n_table_values,
        },
        "notes": [],
        "evidence": [
            {
                "issue_type": i.get("issue_type"),
                "severity": i.get("severity") or _infer_severity(i),
                "explanation": i.get("explanation"),
            }
            for i in (consistency_issues or [])[:12]
        ],
    }


def _infer_severity(issue: dict[str, Any]) -> str:
    conf = str(issue.get("confidence") or "").lower()
    itype = str(issue.get("issue_type") or "").lower()
    expl = str(issue.get("explanation") or "").lower()
    if "sample size" in expl or itype == "number_mismatch" and "n=" in expl:
        return "critical"
    if itype in {"number_mismatch", "unsupported_claim"} and conf == "high":
        return "high"
    if conf == "medium":
        return "medium"
    return "low"


def score_statistical_reporting(
    *,
    claims: list[dict[str, Any]],
    table_values: list[dict[str, Any]],
    notes: list[dict[str, Any]],
    section_map: dict[str, Any],
    llm_assessment: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    text_blobs = " ".join(
        [
            *(str(c.get("text_span") or c.get("value") or "") for c in claims or []),
            *(str(t.get("raw_span") or t.get("value") or "") for t in table_values or []),
            *(str(n.get("text") or "") for n in notes or []),
        ]
    ).lower()

    has_n = any(c.get("claim_type") == "sample_size" for c in claims or []) or " n=" in f" {text_blobs}" or "n=" in text_blobs
    has_effect = any(c.get("claim_type") in {"or_ci", "difference", "rate", "mean"} for c in claims or [])
    has_uncertainty = "95% ci" in text_blobs or "ci " in text_blobs or "confidence" in text_blobs or " se" in text_blobs
    has_p = any(c.get("claim_type") == "p_value" for c in claims or []) or "p=" in text_blobs or "p-value" in text_blobs
    has_method = bool(section_map.get("methods"))
    p_missing_in_table = any(
        (not n.get("contains_p_value")) and "p-value" in str(n.get("text") or "").lower() and "not reported" in str(n.get("text") or "").lower()
        for n in notes or []
    )
    source = "heuristic"

    llm = llm_assessment or {}
    if str(llm.get("status") or "").lower() == "assessed" and float(llm.get("confidence") or 0) >= 0.35:
        has_n = bool(llm.get("has_sample_size", has_n))
        has_effect = bool(llm.get("has_effect", has_effect))
        has_uncertainty = bool(llm.get("has_uncertainty", has_uncertainty))
        has_p = bool(llm.get("has_p_or_bayesian", has_p))
        has_method = bool(llm.get("has_methods_section", has_method))
        p_missing_in_table = bool(llm.get("p_asserted_but_table_missing", p_missing_in_table and has_p))
        source = str(llm.get("source") or "llm")

    credits = [has_n, has_effect, has_uncertainty, has_p, has_method]
    rate = sum(1 for c in credits if c) / 5.0
    penalty = -0.20 if has_p and p_missing_in_table else 0.0
    final_rate = _clamp(rate + penalty)

    return {
        "score": _score_from_rate(final_rate),
        "weight": WEIGHTS["statistical_reporting"],
        "status": "assessed",
        "metrics": {
            "has_sample_size": has_n,
            "has_effect": has_effect,
            "has_uncertainty": has_uncertainty,
            "has_p_or_bayesian": has_p,
            "has_methods_section": has_method,
            "p_asserted_but_table_missing": bool(has_p and p_missing_in_table),
            "rate": final_rate,
            "assessment_source": source,
        },
        "notes": (
            ["Draft asserts p-value but table notes say p-value not reported (−0.20)."]
            if has_p and p_missing_in_table
            else []
        )
        + list(llm.get("notes") or [])[:3],
        "evidence": [],
    }


def score_citation_quality(
    references: list[dict[str, Any]],
    llm_assessment: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    refs = references or []
    llm = llm_assessment or {}
    use_llm = str(llm.get("status") or "").lower() == "assessed" and float(llm.get("confidence") or 0) >= 0.35

    if use_llm:
        doi_coverage = float(llm.get("doi_coverage") or 0.0)
        year_match_rate = float(llm.get("year_match_rate") or 0.0)
        cited_coverage = float(llm.get("cited_reference_coverage") or 0.0)
        orphan_share = float(llm.get("orphan_ref_share") or 0.0)
        missing_meta = int(llm.get("missing_critical_meta_count") or 0)
        meta_penalty = min(0.20, 0.05 * missing_meta)
        rate = _clamp(
            0.40 * doi_coverage
            + 0.30 * year_match_rate
            + 0.20 * cited_coverage
            + 0.10 * (1.0 - orphan_share)
            - meta_penalty
        )
        return {
            "score": _score_from_rate(rate),
            "weight": WEIGHTS["citation_quality"],
            "status": "assessed",
            "metrics": {
                "doi_coverage": doi_coverage,
                "year_match_rate": year_match_rate,
                "cited_reference_coverage": cited_coverage,
                "orphan_ref_share": orphan_share,
                "missing_critical_meta_penalty": meta_penalty,
                "rate": rate,
                "assessment_source": str(llm.get("source") or "llm"),
            },
            "notes": list(llm.get("notes") or [])[:4],
            "evidence": list(llm.get("issues") or [])[:10],
        }

    if not refs:
        return {
            "score": 0,
            "weight": WEIGHTS["citation_quality"],
            "status": "assessed",
            "metrics": {"rate": 0.0, "assessment_source": "heuristic"},
            "notes": ["No references provided."],
            "evidence": [],
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
    cited_coverage = (len(cited) / n) if n else 0.0
    orphans = [r for r in refs if r.get("cited") is False]
    orphan_share = len(orphans) / n if n else 0.0
    doi_coverage = doi_ok / n
    missing_meta = sum(
        1
        for r in refs
        if (not r.get("doi") or str(r.get("doi")).lower() in {"missing", "none", ""})
        and not r.get("year")
    )
    meta_penalty = min(0.20, 0.05 * missing_meta)
    rate = _clamp(
        0.40 * doi_coverage
        + 0.30 * year_match_rate
        + 0.20 * cited_coverage
        + 0.10 * (1.0 - orphan_share)
        - meta_penalty
    )

    return {
        "score": _score_from_rate(rate),
        "weight": WEIGHTS["citation_quality"],
        "status": "assessed",
        "metrics": {
            "doi_coverage": doi_coverage,
            "year_match_rate": year_match_rate,
            "cited_reference_coverage": cited_coverage,
            "orphan_ref_share": orphan_share,
            "missing_critical_meta_penalty": meta_penalty,
            "rate": rate,
            "assessment_source": "heuristic",
        },
        "notes": [],
        "evidence": [
            {"id": r.get("id"), "status": r.get("status"), "doi": r.get("doi")}
            for r in refs
            if "conflict" in str(r.get("status") or "").lower() or str(r.get("doi") or "").lower() == "missing"
        ][:10],
    }


def score_internal_consistency(
    consistency_issues: list[dict[str, Any]],
    meeting_actions: list[dict[str, Any]],
    llm_assessment: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    score = 100
    dup_pen = 0
    unowned_pen = 0
    contra_pen = 0
    source = "heuristic"

    for issue in consistency_issues or []:
        itype = str(issue.get("issue_type") or "").lower()
        if itype == "duplication":
            dup_pen = min(24, dup_pen + 8)
        if itype in {"contradiction", "qualitative_contradiction"}:
            contra_pen = min(20, contra_pen + 10)

    llm = llm_assessment or {}
    if str(llm.get("status") or "").lower() == "assessed" and float(llm.get("confidence") or 0) >= 0.35:
        source = str(llm.get("source") or "llm")
        dup_count = int(llm.get("duplication_count") or 0)
        contra_count = int(llm.get("contradiction_count") or 0)
        # Take the stronger of structured issues vs LLM counts
        dup_pen = max(dup_pen, min(24, dup_count * 8))
        contra_pen = max(contra_pen, min(20, contra_count * 10))

    for action in meeting_actions or []:
        owner = action.get("owner")
        if owner is None or str(owner).strip() == "" or str(owner).upper() == "UNASSIGNED":
            unowned_pen = min(18, unowned_pen + 6)

    score = max(0, score - dup_pen - unowned_pen - contra_pen)
    return {
        "score": score,
        "weight": WEIGHTS["internal_consistency"],
        "status": "assessed",
        "metrics": {
            "duplication_penalty": dup_pen,
            "unowned_action_penalty": unowned_pen,
            "contradiction_penalty": contra_pen,
            "assessment_source": source,
        },
        "notes": list(llm.get("notes") or [])[:3],
        "evidence": list(llm.get("findings") or [])[:8],
    }


def _apply_floors(
    *,
    raw_band: str,
    dimensions: dict[str, Any],
    consistency_issues: list[dict[str, Any]],
    ethics: dict[str, Any],
) -> tuple[str, list[str]]:
    band = raw_band
    notes: list[str] = []

    ce = dimensions["claim_evidence_integrity"]["score"]
    if ce < 55:
        band = _stricter(band, "no-go")
        notes.append(f"Floor: claim_evidence_integrity={ce} < 55 → no-go")
    elif ce < 75:
        band = _stricter(band, "caution")
        notes.append(f"Floor: claim_evidence_integrity={ce} in 55–74 → cap caution")

    stat = dimensions["statistical_reporting"]["score"]
    if stat < 55:
        band = _stricter(band, "caution")
        notes.append(f"Floor: statistical_reporting={stat} < 55 → cap caution")

    critical = 0
    high = 0
    for i in consistency_issues or []:
        sev = str(i.get("severity") or _infer_severity(i)).lower()
        if sev == "critical":
            critical += 1
        if sev == "high":
            high += 1
        if "sample size" in str(i.get("explanation") or "").lower():
            critical += 1
    # de-dup rough double count
    critical = min(critical, len(consistency_issues or []))
    if critical >= 1:
        band = _stricter(band, "no-go")
        notes.append("Floor: ≥1 critical claim–evidence issue → no-go")
    if high >= 5:
        band = _stricter(band, "caution")
        notes.append("Floor: ≥5 high-severity consistency issues → cap caution")

    ethics_dim = dimensions["ethics_compliance"]
    if ethics_dim.get("status") == "assessed" and ethics_dim.get("score") is not None:
        es = int(ethics_dim["score"])
        if es < 50:
            band = _stricter(band, "no-go")
            notes.append(f"Floor: ethics_compliance={es} < 50 → no-go")
        elif es < 70:
            band = _stricter(band, "caution")
            notes.append(f"Floor: ethics_compliance={es} in 50–69 → cap caution")
        if (
            ethics.get("study_involves_human_subjects")
            and str(ethics.get("irb_status") or "").lower() == "missing"
        ):
            band = _stricter(band, "caution")
            notes.append("Floor: human-subjects study with irb_status=missing → cap caution")

    return band, notes


def assemble_research_readiness_scorecard_v1(
    *,
    section_map: dict[str, Any],
    claims: list[dict[str, Any]],
    table_values: list[dict[str, Any]],
    table_notes: Optional[list[dict[str, Any]]] = None,
    consistency_issues: list[dict[str, Any]],
    references: list[dict[str, Any]],
    meeting_actions: Optional[list[dict[str, Any]]] = None,
    ethics_compliance: Optional[dict[str, Any]] = None,
    llm_assessments: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Assemble the v1 research readiness scorecard payload."""
    table_notes = table_notes or []
    meeting_actions = meeting_actions or []
    ethics_compliance = ethics_compliance or {"status": "not_assessed", "notes": ["No ethics artifact provided."]}
    llm_assessments = llm_assessments or {}

    dimensions = {
        "section_coverage": score_section_coverage(section_map),
        "claim_evidence_integrity": score_claim_evidence(
            consistency_issues,
            n_claims=len(claims or []),
            n_table_values=len(table_values or []),
        ),
        "statistical_reporting": score_statistical_reporting(
            claims=claims,
            table_values=table_values,
            notes=table_notes,
            section_map=section_map,
            llm_assessment=llm_assessments.get("statistical_reporting"),
        ),
        "citation_quality": score_citation_quality(
            references,
            llm_assessment=llm_assessments.get("citation"),
        ),
        "internal_consistency": score_internal_consistency(
            consistency_issues,
            meeting_actions,
            llm_assessment=llm_assessments.get("narrative_consistency"),
        ),
        "ethics_compliance": ethics_dimension_score(ethics_compliance),
    }

    # Weighted overall with ethics renormalization when not_assessed
    active: list[tuple[str, float, int]] = []
    for name, dim in dimensions.items():
        if dim.get("status") == "not_assessed" or dim.get("score") is None:
            continue
        active.append((name, float(dim["weight"]), int(dim["score"])))

    if not active:
        overall = 0
    else:
        w_sum = sum(w for _, w, _ in active)
        overall = int(round(sum((w / w_sum) * s for _, w, s in active)))

    raw_band = _band_from_score(overall)
    final_band, floor_notes = _apply_floors(
        raw_band=raw_band,
        dimensions=dimensions,
        consistency_issues=consistency_issues,
        ethics=ethics_compliance,
    )

    issues, remediations = _build_issues_and_remediations(dimensions, consistency_issues, meeting_actions, ethics_compliance)

    return {
        "overall_score": overall,
        "readiness": final_band,
        "readiness_band_raw": raw_band,
        "band_floors": {"applied_notes": floor_notes},
        "dimension_weights": {
            k: (None if dimensions[k].get("status") == "not_assessed" else v)
            for k, v in WEIGHTS.items()
        },
        "dimensions": dimensions,
        "issues": issues,
        "remediations": remediations,
        "ethics_compliance_summary": {
            "status": ethics_compliance.get("status"),
            "irb_status": ethics_compliance.get("irb_status"),
            "consent_status": ethics_compliance.get("consent_status"),
            "llm_provider": ethics_compliance.get("llm_provider"),
        },
        "llm_assessment_summary": {
            "source": llm_assessments.get("source"),
            "provider": llm_assessments.get("llm_provider"),
            "extra_claim_issues": len(llm_assessments.get("claim_evidence_issues") or []),
        },
        "scorecard_version": SCORECARD_VERSION,
    }


def _build_issues_and_remediations(
    dimensions: dict[str, Any],
    consistency_issues: list[dict[str, Any]],
    meeting_actions: list[dict[str, Any]],
    ethics: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    issues: list[dict[str, Any]] = []
    remediations: list[dict[str, Any]] = []

    for i in consistency_issues or []:
        sev = str(i.get("severity") or _infer_severity(i)).lower()
        level = "blocker" if sev == "critical" else ("warning" if sev in {"high", "medium"} else "info")
        issues.append(
            {
                "level": level,
                "source": "consistency_issues",
                "type": i.get("issue_type"),
                "message": i.get("explanation") or i.get("suggested_fix") or "Consistency issue",
            }
        )
        if i.get("suggested_fix"):
            remediations.append({"action": i["suggested_fix"], "priority": level})

    for a in meeting_actions or []:
        owner = a.get("owner")
        if owner is None or str(owner).strip() == "" or str(owner).upper() == "UNASSIGNED":
            issues.append(
                {
                    "level": "warning",
                    "source": "meeting_actions",
                    "type": "unowned_action",
                    "message": a.get("task") or "Unassigned action item",
                }
            )
            remediations.append({"action": f"Assign owner for: {a.get('task')}", "priority": "warning"})

    ce = dimensions["claim_evidence_integrity"]["score"]
    if ce < 75:
        remediations.append(
            {
                "action": "Reconcile draft quantitative claims against primary results tables before submission.",
                "priority": "blocker" if ce < 55 else "warning",
            }
        )

    if ethics.get("status") == "assessed" and str(ethics.get("irb_status") or "").lower() == "missing":
        issues.append(
            {
                "level": "warning",
                "source": "ethics_compliance",
                "type": "irb_missing",
                "message": "Human-subjects study language without clear IRB statement.",
            }
        )

    return issues, remediations

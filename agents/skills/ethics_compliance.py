"""Ethics & compliance skill — LLM-assisted classification for research packages."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from agents.llm.client import LLMClient, LLMMessage, get_default_client

CLARITY_MAP = {
    "approved": 1.0,
    "mentioned": 0.7,
    "mentioned_unclear": 0.45,
    "unclear": 0.35,
    "missing": 0.0,
    "not_applicable": 1.0,
}


def _clarity(status: str | None) -> float:
    if not status:
        return 0.0
    return CLARITY_MAP.get(str(status).lower(), 0.2)


def classify_ethics_compliance(
    *,
    draft_text: str,
    client: Optional[LLMClient] = None,
    out_path: Optional[Path] = None,
) -> dict[str, Any]:
    """Call LLM (or placeholder) to label ethics/compliance signals in the draft."""
    client = client or get_default_client()

    system = (
        "You are a research ethics compliance classifier for manuscript readiness. "
        "Return JSON only. Never invent IRB approvals, consent forms, or registry IDs. "
        "If evidence is missing, use missing/unclear/not_assessed — do not fabricate."
    )
    user = f"""Classify ethics and compliance language in this manuscript excerpt.

Return JSON with keys:
status (assessed|not_assessed),
study_involves_human_subjects (bool),
irb_status (approved|mentioned|mentioned_unclear|missing|not_applicable),
consent_status (approved|mentioned|mentioned_unclear|missing|not_applicable),
data_use_status (clear|unclear|missing|not_applicable),
trial_registry_status (registered|mentioned|missing|not_applicable),
evidence_spans (list of exact quotes),
notes (list of strings),
confidence (0-1).

MANUSCRIPT:
{draft_text[:12000]}
"""

    parsed, resp = client.complete_json(
        [LLMMessage("system", system), LLMMessage("user", user)],
        temperature=0.0,
    )

    if not parsed:
        result = {
            "status": "not_assessed",
            "study_involves_human_subjects": None,
            "irb_status": "unclear",
            "consent_status": "unclear",
            "data_use_status": "unclear",
            "trial_registry_status": "unclear",
            "evidence_spans": [],
            "notes": [resp.error or "LLM returned no parseable JSON"],
            "confidence": 0.0,
            "llm_provider": resp.provider,
            "llm_model": resp.model,
        }
    else:
        result = dict(parsed)
        result["llm_provider"] = resp.provider
        result["llm_model"] = resp.model
        result.setdefault("status", "not_assessed")
        result.setdefault("notes", [])
        # Gate: low confidence or empty spans on human-subjects claims → not_assessed
        if result.get("study_involves_human_subjects") and float(result.get("confidence") or 0) < 0.15:
            if not result.get("evidence_spans"):
                result["status"] = "not_assessed"
                result["notes"] = list(result.get("notes") or []) + [
                    "Downgraded to not_assessed: insufficient evidence spans/confidence."
                ]

    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

    return result


def ethics_dimension_score(ethics: dict[str, Any]) -> dict[str, Any]:
    """Convert ethics artifact into a dimension payload (score only if assessed)."""
    status = str(ethics.get("status") or "not_assessed").lower()
    if status != "assessed":
        return {
            "score": None,
            "weight": 0.05,
            "status": "not_assessed",
            "metrics": {"raw_status": status},
            "notes": ethics.get("notes") or ["Ethics dimension excluded from overall score."],
            "evidence": ethics.get("evidence_spans") or [],
        }

    human = bool(ethics.get("study_involves_human_subjects"))
    irb = _clarity(ethics.get("irb_status"))
    consent = _clarity(ethics.get("consent_status"))
    data_use = _clarity(ethics.get("data_use_status"))
    registry = _clarity(ethics.get("trial_registry_status"))

    if human:
        rate = 0.40 * irb + 0.30 * consent + 0.20 * data_use + 0.10 * registry
    else:
        # Redistribute registry weight when not interventional / not human subjects
        rate = 0.45 * irb + 0.35 * consent + 0.20 * data_use

    score = int(round(100 * max(0.0, min(1.0, rate))))
    return {
        "score": score,
        "weight": 0.05,
        "status": "assessed",
        "metrics": {
            "irb_clarity": irb,
            "consent_clarity": consent,
            "data_use_clarity": data_use,
            "trial_registry_clarity": registry,
            "human_subjects": human,
            "confidence": ethics.get("confidence"),
        },
        "notes": ethics.get("notes") or [],
        "evidence": ethics.get("evidence_spans") or [],
    }

# Research Readiness Scorecard — Scoring Methodology (v1)

This document describes **how** the Research Readiness Scorecard is calculated.

| Status | Version | Notes |
|--------|---------|--------|
| **Current** | **v1** | Six research dimensions + LLM ethics/compliance (soft dims cannot mask claim–evidence failures) |

**Implementation:** `agents/skills/research_readiness_v1.py`  
**Ethics classifier:** `agents/skills/ethics_compliance.py`  
**Orchestrator:** `agents/agent.py`  
**LLM client:** `agents/llm/client.py` (`placeholder` · OpenAI-compatible)  
**Output artifacts:** `research_readiness_scorecard_v1.json`, `ethics_compliance.json`  
**Question answered:** *Is this research package ready for reliable peer-reviewed submission — and what blocks us?*  
**Companion docs:** [PIPELINE.md](PIPELINE.md) · [ARCHITECTURE.md](ARCHITECTURE.md) · [DATA_CONTRACT.md](DATA_CONTRACT.md) · [USAGE.md](USAGE.md) · [INTERPRETING_RESULTS.md](INTERPRETING_RESULTS.md)

**Design inspiration:** Same scorecard architecture as AI Readiness v5.1 (weighted dimensions, bands, hard floors, `not_assessed` gates), with **research** criteria instead of dataset join/DQ criteria.

---

## 1. Purpose and design goals

| Output | Meaning |
|--------|---------|
| **Overall score (0–100)** | Weighted average of the dimensions |
| **Readiness band** | `go` · `caution` · `no-go` |
| **Dimension scores** | Section coverage, Claim–evidence integrity, Statistical reporting, Citation quality, Internal consistency, Ethics & compliance |
| **Issues + remediations** | Prioritized blockers / warnings / info |

**Design principles:**

1. Score the **submission-critical core** only (primary manuscript + primary results tables + cited references).
2. Prefer **measured claim–evidence integrity** over soft narrative polish.
3. Prefer **explicit statistical reporting** (n, effect, CI/p) over “results look fine.”
4. Do not let ethics prose or nice writing average away **number mismatches** or **missing stats**.
5. Use **LLM only** for ethics/compliance language classification; numeric scoring stays deterministic.
6. Missing ethics metadata is `not_assessed`, not a fake zero.
7. Do not invent IRB approvals, consent status, or registry IDs.
8. Soft “well written / well cited” signals must not mask claim–table contradictions.

---

## 2. Inputs (pipeline artifacts)

| Artifact | Role |
|----------|------|
| `section_map.json` | Which IMRaD / required sections exist |
| `claims.json` | Extracted quantitative / citation claims from draft |
| `table_values.json` | Extracted results-table values + notes |
| `consistency_issues.json` | Auditor flags (mismatches, unsupported claims, …) |
| `references.json` | Reference library metadata (year, DOI, cited?) |
| `meeting_actions.json` | Optional coordinator gaps (unowned tasks) |
| `ethics_compliance.json` | IRB / consent / data-use labels (LLM + checklist) |

The scorecard does **not** re-open Word/PDF sources; it scores artifacts only.

---

## 3. Scoping

| Class | Role |
|-------|------|
| **Primary package** | Main draft + primary outcome table(s) + in-text citations — denominator for every dimension |
| **Supplemental** | Appendices / extra tables — minor bonuses only |
| **Out of scope** | Cover art, unrelated notes — excluded |

---

## 4. Overall score and weights

### 4.1 Weights (v1)

| Dimension | Weight | Rationale |
|-----------|-------:|-----------|
| Section coverage | **10%** | Soft structure signal |
| Claim–evidence integrity | **35%** | Hard blocker (like join integrity in AI readiness) |
| Statistical reporting | **20%** | Core scientific completeness |
| Citation quality | **15%** | Provenance / submission hygiene |
| Internal consistency | **15%** | Duplication, contradictions, unowned gaps |
| Ethics & compliance | **5%** | Important, but must not cushion numeric failures |

### 4.2 Overall formula

```text
overall_score =
    round(
        section_coverage_score      * 0.10
      + claim_evidence_score        * 0.35
      + statistical_reporting_score * 0.20
      + citation_quality_score      * 0.15
      + internal_consistency_score  * 0.15
      + ethics_compliance_score     * 0.05   # only when status = assessed
    )
```

When ethics is **`not_assessed`**, its weight is **0** and the other dimensions are renormalized.

```text
score = round(100 * clamp(rate, 0, 1))
```

---

## 5. Readiness band (including hard floors)

### 5.1 Score-based bands (baseline)

| Band | Overall score |
|------|----------------|
| **go** | ≥ 75 |
| **caution** | 50–74 |
| **no-go** | < 50 |

### 5.2 Claim–evidence floors

| Claim–evidence score | Final band rule |
|----------------------|-----------------|
| **< 55** | Forced **`no-go`** |
| **55–74** | Cap at **`caution`** |
| **≥ 75** | Use score-based band (still subject to other floors) |

### 5.3 Statistical & issue floors

| Condition | Final band rule |
|-----------|-----------------|
| Statistical reporting **< 55** | Cap at **`caution`** |
| ≥ **1** `critical` claim–evidence issue (e.g. primary n mismatch) | Forced **`no-go`** |
| ≥ **5** high-severity consistency issues | Cap at **`caution`** |

### 5.4 Ethics floors (assessed only)

| Condition | Final band rule |
|-----------|-----------------|
| Ethics **< 50** | Forced **`no-go`** |
| Ethics **50–69** | Cap at **`caution`** |
| Required human-subjects study with `irb_status=missing` | Cap at **`caution`** |

No ethics floors when `not_assessed`.

**Floor precedence:** apply all floors independently; the **stricter** band wins (`no-go` > `caution` > `go`).

Payload fields: `readiness`, `readiness_band_raw`, `band_floors.applied_notes`.

---

## 6. Dimension methodologies

### 6.1 Section coverage (10%)

**Goal:** Required research sections are present.

Required core: `title`, `abstract`, `introduction`, `methods`, `results`, `discussion`, `references`.  
Optional bonus: `limitations`, `data_availability`, `funding`, `conflicts`.

```text
core_rate  = (# present required sections) / (# required sections)
bonus      = min(0.10, 0.025 * (# present optional sections))
rate       = clamp(core_rate + bonus, 0, 1)
score      = round(100 * rate)
```

---

### 6.2 Claim–evidence integrity (35%)

**Goal:** Quantitative claims in the draft resolve cleanly against tables/notes.

Issue severity weights (from `consistency_issues.json`):

| Severity / type | Penalty |
|-----------------|--------:|
| critical `number_mismatch` on sample size / primary endpoint | 0.25 each (cap 0.50) |
| high `number_mismatch` / `unsupported_claim` | 0.10 each (cap 0.30) |
| medium issues | 0.05 each (cap 0.15) |
| low issues | 0.02 each (cap 0.05) |

```text
rate  = 1.0 - sum(penalties)
score = round(100 * clamp(rate, 0, 1))
```

If no claims and no table values → score **0** (cannot verify).

---

### 6.3 Statistical reporting (20%)

**Goal:** Primary results report the minimum statistical bundle.

Checklist credits (equal weight unless noted):

| Item | Credit if present |
|------|-------------------|
| Sample size (n) | 1 |
| Primary effect estimate | 1 |
| Uncertainty (CI **or** SE) | 1 |
| p-value **or** explicit Bayesian interval | 1 |
| Analysis method named in Methods | 1 |

```text
rate  = sum(credits) / 5
# penalty if draft asserts p-value but table marks p as not reported: -0.20
score = round(100 * clamp(rate + penalties, 0, 1))
```

---

### 6.4 Citation quality (15%)

**Goal:** In-text citations match a complete, consistent reference library.

```text
rate = 0.40 * doi_coverage
     + 0.30 * year_match_rate
     + 0.20 * cited_reference_coverage   # refs actually cited
     + 0.10 * (1 - orphan_ref_share)     # refs never cited
score = round(100 * clamp(rate - missing_critical_meta_penalty, 0, 1))
```

`missing_critical_meta_penalty` = min(0.20, 0.05 × refs missing both DOI and year).

---

### 6.5 Internal consistency (15%)

**Goal:** Package is internally coherent for coordination/submission.

Starts at 100, subtract:

| Signal | Points |
|--------|-------:|
| Near-duplicate discussion claims | 8 each (cap 24) |
| Unowned meeting actions | 6 each (cap 18) |
| Contradictory qualitative statements | 10 each (cap 20) |

```text
score = max(0, 100 - penalties)
```

---

### 6.6 Ethics & compliance (5%)

**Pipeline:** `classify_ethics_compliance` (LLM placeholder) → `ethics_compliance.json`.

**Assessment gate:** enough evidence spans labeled → `assessed`; else `not_assessed` (excluded from overall).

Signals (when assessed):

```text
base_rate = 0.40 * irb_clarity
          + 0.30 * consent_clarity
          + 0.20 * data_use_clarity
          + 0.10 * trial_registry_clarity   # if interventional; else redistribute
```

LLM must **not** invent approvals. Unknown → `not_assessed` / `unclear`, never fake “approved.”

---

## 7. Issues and remediations

Built from consistency issues, weak dimensions, citation gaps, unowned actions, and ethics gaps. Numeric score uses dimensions only.

---

## 8. Output schema

`research_readiness_scorecard_v1.json`:

```text
overall_score
readiness / readiness_band_raw
band_floors
dimension_weights
dimensions.{name}.score|weight|status|metrics|notes|evidence
issues / remediations
ethics_compliance_summary
scorecard_version = "v1"
```

---

## 9. Worked intuition (sample fixture)

Planted primary **n** mismatch (142 vs 148) + missing DOI + unowned ScholarOne task.  
Illustrative live run on `fixtures/sample_package`:

| Dimension | Score |
|-----------|------:|
| Section coverage | 100 |
| Claim–evidence | **48** (critical n mismatch) |
| Statistical reporting | 80 |
| Citation quality | 75 |
| Internal consistency | 86 |
| Ethics | **39** (`assessed`, IRB/consent unclear) |

| Field | Value |
|-------|------:|
| Overall | 69 |
| Raw band | caution |
| Final readiness | **`no-go`** |

Soft strengths do not rescue critical claim–evidence / ethics floors.

---

## 10. Implementation map

| Concern | Module |
|---------|--------|
| v1 scoring + assembly | `agents/skills/research_readiness_v1.py` |
| LLM ethics | `agents/skills/ethics_compliance.py` |
| LLM client | `agents/llm/client.py` |
| Pipeline wiring | `agents/agent.py` → `assemble_research_readiness_scorecard_v1` |
| Unit tests | `tests/test_research_readiness_v1.py` |
| Sample package | `fixtures/sample_package/` |

---

## 11. Limits and non-claims

- Does not prove scientific correctness or novelty.
- Does not replace peer review or biostatistician sign-off.
- LLM ethics labels are inferred language signals, not legal/IRB certification.
- Does not invent registry IDs, approvals, or consent forms.
- Band floors are intentionally conservative for submission-critical packages.

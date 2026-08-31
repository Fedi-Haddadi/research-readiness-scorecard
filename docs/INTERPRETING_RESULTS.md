# Interpreting results

## Read these fields first

From `research_readiness_scorecard_v1.json`:

1. **`readiness`** — final go / caution / no-go (after floors)
2. **`overall_score`** — 0–100 weighted average
3. **`readiness_band_raw`** — band from score alone (before floors)
4. **`band_floors.applied_notes`** — why final band differs from raw
5. **`issues`** + **`remediations`** — what to fix

If `readiness` ≠ `readiness_band_raw`, floors decided the outcome. Trust **`readiness`**.

## Bands

| Band | Typical meaning |
|------|-----------------|
| `go` | No hard floors failed; overall ≥ 75 |
| `caution` | Submittable only after fixes, or soft floors capped the band |
| `no-go` | Critical integrity/ethics/stat floors failed — do not treat as submission-ready |

## Dimension cheat sheet

| Dimension | High score means | Low score means |
|-----------|------------------|-----------------|
| Section coverage | IMRaD skeleton present | Missing methods/results/refs/etc. |
| Claim–evidence | Draft numbers match tables | n/rate/p mismatches or unverifiable package |
| Statistical reporting | n, effect, CI/p, methods present | Incomplete reporting bundle |
| Citation quality | DOIs, years align, few orphans | Missing DOI, year conflicts, orphans |
| Internal consistency | Little duplication / owned tasks | Repeated claims, unassigned work |
| Ethics | Clear IRB/consent/data-use language | Missing/unclear human-subjects compliance text |

## Worked example (`fixtures/sample_package`)

Illustrative live run with model-assisted ethics:

| Field | Value |
|-------|------:|
| `overall_score` | 69 |
| `readiness_band_raw` | caution |
| `readiness` | **no-go** |

| Dimension | Score |
|-----------|------:|
| Section coverage | 100 |
| Claim–evidence | 48 |
| Statistical reporting | 80 |
| Citation quality | 75 |
| Internal consistency | 86 |
| Ethics | 39 |

**Why no-go despite “mostly fine” dimensions?**

- Claim–evidence 48 &lt; 55 floor
- Critical sample size mismatch (142 vs 148)
- Ethics 39 &lt; 50 floor (IRB/consent mentioned but unclear)

This is intentional: the system is conservative, like AI Readiness v5.1 floors on weak joins.

## Ethics artifact

In `ethics_compliance.json`, prefer:

- **`evidence_spans`** that quote the draft
- **`confidence`**
- statuses like `mentioned_unclear` over invented `approved`

If `status` is `not_assessed`, ethics did not enter the overall average; check `notes` for why.

## What a good remediation pass looks like

1. Fix all `blocker` issues (usually primary n / endpoint mismatches)
2. Align p-values and CIs between prose and tables
3. Repair citation year/DOI gaps
4. Assign owners on meeting actions
5. Clarify IRB approval / waiver outcome and data-use language in the draft
6. Re-run the scorecard and confirm floors clear

## What the scorecard does *not* mean

- High score ≠ paper will be accepted
- Low ethics score ≠ legal finding of noncompliance
- `go` ≠ biostatistician sign-off

Use it as a **submission-ops readiness gate**, not as peer review.

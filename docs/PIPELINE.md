# Pipeline

This document explains **how a run works**: what enters, what each stage does, and what exits.

## Question answered

*Is this research package ready for reliable peer-reviewed submission — and what blocks us?*

## High-level flow

```text
┌─────────────────────────────────────────────────────────────┐
│ Research package directory                                  │
│  draft.md, section_map.json, claims.json, table_*.json,     │
│  consistency_issues.json, references.json, meeting_actions  │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
                    agents/agent.py  (orchestrator)
                               │
              ┌────────────────┴────────────────┐
              ▼                                 ▼
   ethics_compliance skill              load structured artifacts
   (LLM via agents/llm/client.py)       (no DB / no PDF re-parse)
              │                                 │
              ▼                                 │
   ethics_compliance.json                       │
              │                                 │
              └────────────────┬────────────────┘
                               ▼
              research_readiness_v1 skill
              (deterministic weighted score + floors)
                               │
                               ▼
              research_readiness_scorecard_v1.json
```

## Stages

### 1. Package load

The orchestrator reads JSON/Markdown from `--package`. Missing files default to empty structures (`{}` / `[]`), which usually lowers scores (e.g. no claims/tables → claim–evidence = 0).

The scorecard **does not** open Word/PDF sources at this stage. Upstream tools (or humans) must already have produced the artifacts.

### 2. Ethics classification (LLM skill)

`classify_ethics_compliance(draft_text)` sends the manuscript text to the configured provider with a strict JSON schema:

- Never invent IRB approvals, consent forms, or registry IDs
- Prefer `missing` / `unclear` / `not_assessed` over fabricated “approved”

Writes: `<output>/ethics_compliance.json`

### 2b. Package language reviews (LLM skill)

`assess_package_with_llm(...)` reviews citations, statistical reporting, narrative consistency, and may add extra claim–evidence issues. Offline/`placeholder` uses heuristics. Writes: `<output>/llm_assessments.json`

Providers:

| `LLM_PROVIDER` | Behavior |
|----------------|----------|
| `placeholder` | Offline heuristic stub (no network) |
| `openai` | Live OpenAI-compatible API |

### 3. Deterministic score assembly

`assemble_research_readiness_scorecard_v1(...)` computes six dimension scores from artifacts + ethics result. See [METHODOLOGY.md](METHODOLOGY.md) for formulas.

Key properties:

- Claim–evidence and stats/citation/consistency math are **pure functions** of inputs
- Ethics contributes only when `status == assessed`
- Soft dimensions cannot average away hard blockers because of **band floors**

### 4. Band + floors

1. Compute `overall_score` (0–100)
2. Map to raw band: `go` (≥75) · `caution` (50–74) · `no-go` (&lt;50)
3. Apply floors independently; **stricter** band wins

Example floors:

- Claim–evidence &lt; 55 → force `no-go`
- ≥1 critical claim–evidence issue → force `no-go`
- Ethics &lt; 50 (when assessed) → force `no-go`

### 5. Issues and remediations

The scorecard attaches human-facing:

- **issues** — blockers / warnings / info from consistency flags, unowned actions, ethics gaps
- **remediations** — suggested fixes (often copied from `suggested_fix` on issues)

Numeric score uses dimensions only; issues are explanatory.

## What is *not* in the pipeline (v1)

| Capability | Status |
|------------|--------|
| PDF/DOCX text extraction | Out of scope (bring pre-extracted artifacts) |
| Automatic claim extraction agent | Out of scope (supply `claims.json`) |
| Automatic table parsing | Out of scope (supply `table_values.json`) |
| Journal formatter / ScholarOne upload | Out of scope |
| Scientific peer review | Explicitly not claimed |

Those can sit **upstream** as separate agents that write the package folder this pipeline consumes.

## Runtime entrypoint

```powershell
python -m agents.agent --package fixtures/sample_package
python -m agents.agent --package path\to\package --output path\to\out
python -m agents.agent --package path\to\package --skip-ethics-llm
```

`--skip-ethics-llm` reuses `ethics_compliance.json` from the package if present; otherwise the LLM/placeholder path still runs when the file is missing.

## Related docs

- [ARCHITECTURE.md](ARCHITECTURE.md) — module boundaries
- [DATA_CONTRACT.md](DATA_CONTRACT.md) — schemas
- [INTERPRETING_RESULTS.md](INTERPRETING_RESULTS.md) — reading the JSON
- [USAGE.md](USAGE.md) — setup and operations

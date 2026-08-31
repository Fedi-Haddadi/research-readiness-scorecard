# Research Readiness Scorecard

Agent-based scorecard that answers:

> **Is this research package ready for reliable peer-reviewed submission — and what blocks us?**

It uses weighted dimensions, readiness bands (`go` / `caution` / `no-go`), hard floors, and optional LLM review where language understanding improves accuracy.

| | |
|---|---|
| **Version** | v1 |
| **Orchestrator** | `agents/agent.py` |
| **Scoring** | `agents/skills/research_readiness_v1.py` |
| **LLM reviews** | ethics, citations, stats reporting, narrative consistency, extra claim checks |
| **LLM client** | `agents/llm/client.py` (`placeholder` · OpenAI-compatible) |

---

## Setup

### 1. Clone

```powershell
git clone https://github.com/Fedi-Haddadi/research-readiness-scorecard.git
cd research-readiness-scorecard
```

### 2. Python

- Python **3.10+** (tested on 3.13)
- No pip packages required for placeholder or OpenAI-compatible HTTP mode (stdlib only)

### 3. Configure the LLM provider

```powershell
copy .env.example .env
```

**Offline (no API key):**

```env
LLM_PROVIDER=placeholder
```

**Live chat API (OpenAI-compatible):**

```env
LLM_PROVIDER=openai
LLM_API_KEY=sk-your-key
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini
```

Any OpenAI-compatible endpoint works: set `LLM_BASE_URL` and `LLM_MODEL` to match your provider.

Never commit `.env`. It is gitignored.

### 4. Run the sample package

```powershell
python -m agents.agent --package fixtures/sample_package
```

Outputs:

- `fixtures/sample_package/outputs/research_readiness_scorecard_v1.json`
- `fixtures/sample_package/outputs/ethics_compliance.json`
- `fixtures/sample_package/outputs/llm_assessments.json`

### 5. Tests

```powershell
python -m unittest tests/test_research_readiness_v1.py -v
```

### 6. Your own package

Put artifacts in a folder (`draft.md`, `section_map.json`, `claims.json`, `table_values.json`, `consistency_issues.json`, `references.json`, …) and run:

```powershell
python -m agents.agent --package path\to\your_package --output path\to\out
```

Schemas: [docs/DATA_CONTRACT.md](docs/DATA_CONTRACT.md) · full ops guide: [docs/USAGE.md](docs/USAGE.md).

---

## Dimensions (v1)

| Dimension | Weight | LLM? |
|-----------|-------:|------|
| Section coverage | 10% | No (structured checklist) |
| Claim–evidence integrity | **35%** | **Yes** — LLM can add evidenced mismatches on top of packaged issues |
| Statistical reporting | 20% | **Yes** — finds n / effect / CI / p / methods more reliably than keywords |
| Citation quality | 15% | **Yes** — checks DOI coverage, year conflicts, orphans against the draft |
| Internal consistency | 15% | **Yes** — spots discussion duplication and contradictions |
| Ethics & compliance | 5% | **Yes** (excluded if `not_assessed`) |

Section coverage stays rule-based. Everything language-heavy goes through the model when a live provider is configured; offline mode falls back to heuristics.

Hard floors prevent soft strengths from masking critical draft↔table mismatches.

### Example fixture result

On `fixtures/sample_package` (planted n=142 vs table n=148):

| Field | Value |
|-------|------:|
| Overall | **69** |
| Raw band | caution |
| Final readiness | **`no-go`** |

Floors: claim–evidence &lt; 55, critical sample-size issue, ethics &lt; 50.

---

## Documentation

| Doc | Contents |
|-----|----------|
| [docs/PIPELINE.md](docs/PIPELINE.md) | End-to-end flow |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Agents, skills, LLM boundary |
| [docs/DATA_CONTRACT.md](docs/DATA_CONTRACT.md) | Input/output schemas |
| [docs/USAGE.md](docs/USAGE.md) | Setup, CLI, troubleshooting |
| [docs/INTERPRETING_RESULTS.md](docs/INTERPRETING_RESULTS.md) | Reading scores and bands |
| [docs/METHODOLOGY.md](docs/METHODOLOGY.md) | Formal scoring formulas (v1) |

---

## Repository layout

```text
agents/
  agent.py
  llm/client.py
  skills/
    research_readiness_v1.py
    ethics_compliance.py
    llm_assessments.py
docs/
fixtures/sample_package/
tests/
.env.example
```

---

## Prompts used to build this project

These prompts recreate the project with an AI coding agent. Run them in order.

### Prompt 1 — Product brief

```text
I need a research readiness scorecard. Given a manuscript package, it should tell me if we are ready to submit to a journal and what is blocking us. Score the basics that matter in practice: are the required sections there, do the numbers in the text match the tables, is the stats reporting complete, are the citations clean, is the package internally consistent, and does the ethics wording look clear enough. Keep the numeric formulas stable and rule-based, but use the language model wherever reading the draft carefully would be more accurate than brittle keyword checks, especially for citations, stats reporting, narrative duplication, ethics language, and spotting extra claim-table mismatches. A paper should not look ready just because it is well written if the sample size in the text disagrees with the table. Document the scoring method, with go, caution, and no-go outcomes and hard stop rules.
```

### Prompt 2 — Dimensions and floors

```text
Please finalize the first version of the dimensions and weights. Put the heaviest weight on whether claims match the evidence in the tables. Then weight statistical reporting, citation quality, and internal consistency. Keep section coverage lighter. Give ethics a small weight and leave it out of the overall score when there is not enough to assess. Write the formulas, the penalties, and the rules that force caution or no-go even if the overall average looks okay.
```

### Prompt 3 — Build the system

```text
Build this as a small Python app I can run from the command line. One entry point should load a research package folder, run the model-assisted reviews, compute the scorecard, and write the results out. Prefer an agent-style layout with reusable skills for scoring, ethics, and the other language reviews. For now, score structured package files plus the draft text. Do not try to parse PDFs or connect to a database in this version.
```

### Prompt 4 — Sample package

```text
Create a realistic sample package we can use for testing. Plant a few real problems: the draft says 142 patients while the table says 148, the readmission rate is slightly off, a p-value appears in the text but the table notes say it is not reported, one citation has the wrong year, one reference is missing a DOI, and one submission task has no owner. Also keep a private checklist of the planted issues so we can verify the scorecard catches them.
```

### Prompt 5 — Offline model stub and reviews

```text
Add a thin model client with an offline placeholder mode so the full pipeline still runs without an API key. When live, use the model for ethics, citation quality, statistical reporting, narrative consistency, and extra claim checks. Be careful not to invent IRB approvals, DOIs, or table numbers. If the model cannot assess something fairly, fall back to heuristics and say so.
```

### Prompt 6 — Live model

```text
Connect a real chat API through that same client, keep keys in a local env file that is not committed, run the sample package end to end, and make sure vague IRB or consent wording is labeled as unclear rather than approved.
```

### Prompt 7 — Documentation

```text
Write practical documentation: how to set it up, how the pipeline works, what inputs and outputs look like, how to read the score, and the full scoring methodology. Include these build prompts in the README, and be explicit about the limits so nobody treats the score as peer review or legal clearance.
```

### Prompt 8 — Clean and publish

```text
Remove every secret from the project, double-check nothing sensitive is in git history, then publish it to a new public GitHub repository.
```

### Optional — upstream manuscript auditor

```text
Later we may want help generating the package inputs automatically. If so, build a manuscript auditor that pulls claims from the draft, checks them against tables, filters noisy false alarms, and drafts follow-ups for the submission process, in a format this scorecard can consume.
```

---

## Limits

- Does **not** prove scientific correctness or novelty.
- Does **not** replace biostatistician or IRB review.
- Ethics and citation labels are language signals, not legal certification.
- Numeric scoring still depends on package quality; garbage-in claims/tables produce garbage-out confidence.

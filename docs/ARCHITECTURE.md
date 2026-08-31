# Architecture

## Design goals

1. **Same pattern as AI Readiness** — orchestrator + skills + versioned scorecard assembly + optional LLM skill with `not_assessed` gate.
2. **Hard evidence over soft prose** — claim–evidence integrity dominates weight and floors.
3. **Single LLM boundary** — all model calls go through `agents/llm/client.py`.
4. **Deterministic core** — scoring formulas are testable without a network.

## Component map

```text
agents/
├── agent.py                      # Orchestrator + CLI
├── llm/
│   ├── __init__.py
│   └── client.py                 # LLMClient (placeholder | openai-compatible)
└── skills/
    ├── __init__.py
    ├── ethics_compliance.py      # LLM ethics labels
    ├── llm_assessments.py        # LLM citation/stats/consistency/claim review
    └── research_readiness_v1.py  # Dimension scores + floors → scorecard JSON
```

| Concern | Module | Responsibility |
|---------|--------|----------------|
| Run wiring | `agents/agent.py` | Load package, call skills, write outputs |
| HTTP / providers | `agents/llm/client.py` | `complete` / `complete_json`, `.env` load |
| Ethics labels | `agents/skills/ethics_compliance.py` | Prompt + parse + dimension helper |
| Language reviews | `agents/skills/llm_assessments.py` | Citations, stats, narrative, extra claims |
| Scorecard v1 | `agents/skills/research_readiness_v1.py` | Weights, formulas, floors, issues |

## Agent vs skills

| Term | Meaning here |
|------|----------------|
| **Agent** | Orchestrator that owns I/O and skill order (`run_research_readiness_agent`) |
| **Skill** | Focused function with a clear contract (classify ethics; assemble scorecard) |

Skills are importable and unit-testable on their own. The agent is the composition root.

## LLM boundary

```text
ethics_compliance.classify_ethics_compliance
        │
        ▼
LLMClient.complete_json(messages)
        │
        ├── provider=placeholder → local stub / heuristics
        └── provider=openai      → POST {base}/chat/completions
```

Rules:

- Skills must **not** call `urllib` / vendor SDKs directly
- Missing or unparseable LLM output → ethics `not_assessed` or heuristic fallback for other reviews
- Placeholder exists so CI and demos run offline

### Environment

| Variable | Role |
|----------|------|
| `LLM_PROVIDER` | `placeholder` · `openai` (OpenAI-compatible) |
| `LLM_API_KEY` | Bearer token |
| `LLM_BASE_URL` | API root (e.g. `https://api.openai.com/v1`) |
| `LLM_MODEL` | Model id |

Loaded from process env and project `.env` (UTF-8, BOM-safe). `.env` is gitignored.

## Scoring architecture (mirrors AI Readiness)

| AI Readiness idea | Research Readiness analogue |
|-------------------|-----------------------------|
| Join integrity heavy weight | Claim–evidence integrity (35%) |
| Soft gov weight + floors | Ethics (5%) + ethics floors when assessed |
| `not_assessed` excludes dim | Ethics excluded + weights renormalized |
| Quality findings → consistency | `consistency_issues.json` → claim–evidence + internal consistency |
| Band floors | Claim–evidence / stats / critical issue / ethics floors |

## Extension points

| Want to add… | Where |
|--------------|--------|
| New dimension | `research_readiness_v1.py` + [METHODOLOGY.md](METHODOLOGY.md) |
| New LLM task (e.g. journal fit) | New skill under `agents/skills/` using `LLMClient` |
| New provider | Branch in `LLMClient.complete` |
| Upstream extractors | Separate agents that **write** package JSON this repo consumes |
| Scorecard v2 | New `research_readiness_v2.py`; keep v1 importable |

## Testing shape

- Unit tests call `assemble_research_readiness_scorecard_v1` with in-memory fixtures (no network)
- Optional live checks use `.env` + `fixtures/sample_package` (not required for CI)

## Non-goals of this architecture

- Multi-agent debate / planner loops
- Persistent memory store
- Direct database access
- Guaranteeing IRB or statistical validity

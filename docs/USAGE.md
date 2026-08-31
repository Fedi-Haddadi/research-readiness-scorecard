# Usage

## Requirements

- Python 3.10+ (tested on 3.13)
- Stdlib only for `placeholder` / OpenAI-compatible HTTP calls (no pip install required)

Optional later: vendor SDKs if you prefer them over `urllib` — not required today.

## Setup

```powershell
cd C:\Users\hadda\research-readiness-scorecard
copy .env.example .env
```

Edit `.env`:

```env
LLM_PROVIDER=openai
LLM_API_KEY=sk-your-key
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini
```

Offline:

```env
LLM_PROVIDER=placeholder
```

Any OpenAI-compatible endpoint works via `LLM_BASE_URL` / `LLM_MODEL`.
Never commit `.env`. It is listed in `.gitignore`.

## Run the agent

```powershell
python -m agents.agent --package fixtures/sample_package
```

Custom output directory:

```powershell
python -m agents.agent --package fixtures/sample_package --output outputs\run1
```

Reuse an existing ethics file (skip live LLM when file exists in package):

```powershell
python -m agents.agent --package fixtures/sample_package --skip-ethics-llm
```

### CLI flags

| Flag | Default | Meaning |
|------|---------|---------|
| `--package` | `fixtures/sample_package` | Input package directory |
| `--output` | `<package>/outputs` | Where to write JSON artifacts |
| `--skip-ethics-llm` | off | Prefer package `ethics_compliance.json` if present |

## Prepare your own package

1. Create a folder
2. Add the input files described in [DATA_CONTRACT.md](DATA_CONTRACT.md)
3. Run the agent pointing `--package` at that folder

Minimum useful set:

- `draft.md` (for ethics)
- `section_map.json`
- `claims.json` + `table_values.json` + `consistency_issues.json`
- `references.json`

## Providers

| Provider | When to use |
|----------|-------------|
| `placeholder` | Unit demos, CI without secrets |
| `openai` | Live OpenAI-compatible chat API |

Smoke-test the client:

```powershell
python -c "from agents.llm.client import get_default_client; c=get_default_client(); print(c.provider, c.model); r=c.complete([{'role':'user','content':'ping'}], max_tokens=16); print(r.ok, r.text[:80], r.error)"
```

## Tests

```powershell
python -m unittest tests/test_research_readiness_v1.py -v
```

Tests use in-memory fixtures and the sample package; they do not require a live API key for the critical-path assertion (sample package run will call whatever provider is in `.env` — set `placeholder` for fully offline CI).

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `provider=placeholder` despite `.env` | BOM / env already set / stale shell var | Rewrite `.env` as UTF-8 no BOM; `Remove-Item Env:LLM_PROVIDER` |
| `Missing API key` | Empty `DEEPSEEK_API_KEY` | Set key in `.env` |
| `HTTP 401` | Bad/rotated key | Update key |
| Ethics `not_assessed` always | Empty `draft.md` or parse failure | Check draft + raw LLM error in notes |
| Claim–evidence score 0 | Empty claims and tables | Supply both artifacts |
| Band `no-go` with high overall | Floor fired | Read `band_floors.applied_notes` |

## Related docs

- [PIPELINE.md](PIPELINE.md)
- [ARCHITECTURE.md](ARCHITECTURE.md)
- [METHODOLOGY.md](METHODOLOGY.md)

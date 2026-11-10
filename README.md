# SmartRoute

SmartRoute is an experimental, self-hosted gateway for routing requests to large language models (LLMs). It provides a small FastAPI service, a Streamlit playground, configurable routing policies, response caching, provider resilience, request logging, and an evaluation harness.

The project is intended for learning, local experimentation, and portfolio demonstrations. It is **not production-ready** and should not be exposed to untrusted users without substantial additional security, privacy, and operational work.

## Contents

- [Highlights](#highlights)
- [How a request is handled](#how-a-request-is-handled)
- [Project layout](#project-layout)
- [Requirements](#requirements)
- [Installation and configuration](#installation-and-configuration)
- [Run the gateway and dashboard](#run-the-gateway-and-dashboard)
- [HTTP API](#http-api)
- [Routing strategies](#routing-strategies)
- [Caching](#caching)
- [Provider resilience and cost estimates](#provider-resilience-and-cost-estimates)
- [Evaluation](#evaluation)
- [Tests](#tests)
- [Data, privacy, and security notes](#data-privacy-and-security-notes)
- [Troubleshooting](#troubleshooting)
- [Known limitations](#known-limitations)

## Highlights

- **Complexity-based routing:** a deterministic heuristic classifies prompts as `easy`, `medium`, or `hard`. An optional LLM judge can classify the prompt instead.
- **Comparable routing baselines:** `auto`, `cheapest`, and `strongest` let you compare the router with fixed easy- and hard-tier choices.
- **OpenAI-compatible provider calls:** supports Groq and OpenRouter endpoints, with configurable model IDs and provider preference.
- **Tenant-scoped caching:** exact-match cache entries are isolated by tenant and request context. An optional in-memory semantic cache can reuse answers for sufficiently similar prompts.
- **Resilience controls:** retries with exponential backoff, provider fallback, and an in-memory circuit breaker.
- **Usage and cost visibility:** records request timing, token counts, estimated cost, cache use, and fallback use in SQLite.
- **Interactive dashboard:** submit prompts, inspect aggregate metrics and recent request metadata, and view evaluation reports.
- **Repeatable evaluation:** compare strategies on a CSV benchmark, with optional LLM-as-a-judge scoring.

## How a request is handled

For `POST /chat`, the gateway:

1. Checks the optional API key and applies an in-memory per-tenant request limit.
2. Classifies the prompt with the heuristic, or with the optional routing judge when requested.
3. Applies the selected strategy. `cheapest` selects the `easy` tier and `strongest` selects the `hard` tier.
4. Looks for an exact cache hit, then (if enabled) a semantic cache hit.
5. Calls the configured primary provider and, if needed, retries or tries the fallback provider.
6. Estimates cost from the provider-reported token counts and the configured per-tier prices.
7. Stores the response in enabled caches and logs the request in SQLite.

The heuristic looks for complexity signals such as coding, debugging, architecture, and multi-step analysis; prompt length and code blocks also influence the selected tier. These rules are a simple baseline, not a trained classifier.

## Project layout

```text
.
├── app/
│   ├── cache.py             # Exact-request cache-key construction
│   ├── config.py            # Environment and default configuration
│   ├── database.py          # SQLite schema, logs, metrics, and exact cache
│   ├── main.py              # FastAPI app and /health, /metrics, /chat routes
│   ├── pricing.py           # Token-based cost estimates
│   ├── providers.py         # Provider calls, retries, and fallback
│   ├── resilience.py        # In-memory circuit breaker
│   ├── router.py            # Heuristic and optional LLM-based routing
│   ├── security.py          # Optional API-key check and tenant rate limit
│   └── semantic_cache.py    # Optional in-memory embedding cache
├── evaluation/
│   ├── benchmark.csv        # Prompts, references, and expected tiers
│   ├── run_eval.py          # Strategy comparison and optional judging
│   └── results/             # Locally generated CSV reports (Git-ignored)
├── tests/
│   └── test_router.py       # Heuristic routing tests
├── streamlit_app.py         # Streamlit playground and dashboard
├── requirements.txt         # Core dependencies
└── requirements-semantic.txt
```

## Requirements

- Python 3.11 or newer
- A supported provider API key (Groq or OpenRouter); a provider key is needed to generate responses
- Git, if cloning the repository

The optional semantic cache installs sentence-transformers and its supporting dependencies. Its embedding model is downloaded when first needed, so allow additional disk space, memory, and startup time if enabling it.

## Installation and configuration

From the project directory:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cp .env.example .env
```

On Windows PowerShell, activate the environment with:

```powershell
py -3 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `.env` and add a real provider key. The example file contains blank key fields; do not commit your own `.env` file.

### Configuration reference

All settings are optional unless your chosen operation requires a provider credential. Defaults are provided in `app/config.py` and `.env.example`.

| Variables | Purpose |
|---|---|
| `GROQ_API_KEY`, `OPENROUTER_API_KEY` | Credentials for the corresponding model provider. Configure at least one. |
| `GROQ_BASE_URL`, `OPENROUTER_BASE_URL` | OpenAI-compatible API base URLs for provider requests. |
| `PRIMARY_PROVIDER`, `FALLBACK_PROVIDER` | Provider preference (`groq` or `openrouter`) and optional fallback. Leave fallback empty to disable it. |
| `EASY_MODEL`, `MEDIUM_MODEL`, `HARD_MODEL` | Model IDs mapped to the three routing tiers. |
| `ROUTER_MODEL`, `JUDGE_MODEL` | Models used by the optional routing judge and evaluation judge. |
| `DATABASE_PATH` | SQLite file location; defaults to `smartroute.db` in the current working directory. |
| `EXACT_CACHE_ENABLED`, `CACHE_TTL_SECONDS` | Enable the exact cache and set its time-to-live in seconds. |
| `SEMANTIC_CACHE_ENABLED`, `SEMANTIC_CACHE_THRESHOLD`, `SEMANTIC_MODEL` | Enable and tune the optional semantic cache and its embedding model. |
| `MAX_RETRIES`, `RETRY_BASE_SECONDS` | Number of provider retries and the initial exponential-backoff delay. |
| `CIRCUIT_FAILURE_THRESHOLD`, `CIRCUIT_RESET_SECONDS` | Provider failures before opening the circuit and its reset interval. |
| `API_KEY`, `RATE_LIMIT_PER_MINUTE` | Optional shared API-key check and per-process, per-tenant rate limit. |
| `EASY_INPUT_PRICE_PER_1M`, `EASY_OUTPUT_PRICE_PER_1M` (and `MEDIUM_...`, `HARD_...`) | Illustrative USD input/output prices per one million tokens, used for estimates. |

Model availability, provider APIs, and pricing change over time. Check provider documentation and update the model IDs and price settings before running experiments.

## Run the gateway and dashboard

Start the API from the project root, with the virtual environment activated:

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Useful local endpoints:

- Interactive API documentation: <http://127.0.0.1:8000/docs>
- Health check: <http://127.0.0.1:8000/health>
- Metrics: <http://127.0.0.1:8000/metrics>

In a second terminal, activate the same environment and start the dashboard:

```bash
streamlit run streamlit_app.py
```

Streamlit opens at <http://localhost:8501>. By default, the dashboard uses the API at `http://127.0.0.1:8000`. The dashboard reads request logs and metrics from the same SQLite database; run both processes from the project directory and use the same `DATABASE_PATH` if you override it.

## HTTP API

### `GET /health`

Returns the service status and version. This endpoint does not require the optional API key.

```json
{
  "status": "healthy",
  "version": "7.0.0"
}
```

### `POST /chat`

Required JSON field: `prompt` (1–20,000 characters).

```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: demo" \
  -d '{
    "prompt": "Explain what an API is",
    "system_prompt": "You are a helpful assistant.",
    "strategy": "auto",
    "use_llm_judge": false,
    "use_cache": true,
    "max_tokens": 1000
  }'
```

When `API_KEY` is configured, include `-H "X-API-Key: your-configured-key"`. The tenant header is optional and defaults to `default`; it is a cache/rate-limit namespace, **not an authenticated identity**.

Request fields:

| Field | Type | Default | Description |
|---|---|---|---|
| `prompt` | string | Required | User request, 1–20,000 characters. |
| `system_prompt` | string | `You are a helpful assistant.` | System instruction sent to the model and included in cache context. |
| `strategy` | string | `auto` | One of `auto`, `cheapest`, or `strongest`. |
| `use_llm_judge` | boolean | `false` | Ask the router model to classify prompt complexity; heuristic routing is used otherwise and as fallback. |
| `use_cache` | boolean | `true` | Allow enabled exact and semantic caches to be checked and populated. |
| `max_tokens` | integer | `1000` | Completion limit from 1 through 8,000. |

Successful responses contain the answer, selected model/provider/tier, token counts, estimated cost, latency, cache and fallback flags, route details, and requested strategy. Provider failures are reported as gateway errors.

### `GET /metrics`

Returns aggregate counts and rates from the most recent request records available to the metrics calculation: request count, total estimated cost, average latency, cache-hit rate, and fallback rate. Configure `API_KEY` for the optional key check. Metrics are currently aggregated across tenants rather than filtered by tenant.

## Routing strategies

- **`auto`** uses the heuristic route by default. Set `use_llm_judge` to `true` to request a model-based route.
- **`cheapest`** forces the `easy` tier. This is a fixed-tier comparison baseline, not a guarantee of the lowest possible provider price.
- **`strongest`** forces the `hard` tier. This is a comparison baseline, not a guarantee that a given model is the strongest available.

The selected tier maps to a model ID via `EASY_MODEL`, `MEDIUM_MODEL`, and `HARD_MODEL`. Review the route and model in each response and in the dashboard when comparing results.

## Caching

The exact cache is stored in SQLite. Its key includes the tenant, prompt, system prompt, model, tier, and maximum token count; entries expire after `CACHE_TTL_SECONDS`. Exact cache hits return the saved answer without a provider call and report zero token usage and estimated cost for that request.

The optional semantic cache uses sentence-transformers embeddings and cosine similarity. Enable it with:

```env
SEMANTIC_CACHE_ENABLED=true
```

Install the extra dependencies first:

```bash
python -m pip install -r requirements-semantic.txt
```

The semantic cache is in memory, is cleared on restart, and uses `SEMANTIC_CACHE_THRESHOLD` to decide whether a prior prompt is similar enough. Similar wording does not ensure equivalent intent or a safe answer to reuse. Keep the feature disabled for sensitive, personalized, time-sensitive, or high-consequence requests unless its behavior is suitable for your use case.

## Provider resilience and cost estimates

Provider calls use configured retry/backoff settings. If a distinct fallback provider is configured, the gateway tries it after primary-provider failures; the response indicates whether fallback was used. The circuit breaker tracks failures separately per provider and is held in memory.

Estimated cost is calculated from provider-reported input/output token counts and the corresponding configured tier prices. The values in `.env.example` are illustrative, may become outdated, and do not account for every provider billing detail. They are useful for comparisons, not accounting or billing.

## Evaluation

The benchmark is `evaluation/benchmark.csv`. The evaluator calls a running gateway with caching disabled, compares `auto`, `cheapest`, and `strongest` by default, and can score generated answers with an LLM judge. It calculates strategy-level success/errors, mean judge score, total estimated cost, average latency, and auto-route accuracy where expected tiers are present.

With the API running, use another terminal:

```bash
# Small smoke evaluation
python evaluation/run_eval.py --limit 5

# Full benchmark
python evaluation/run_eval.py

# Skip LLM-as-a-judge calls
python evaluation/run_eval.py --limit 10 --no-judge

# Choose strategies explicitly
python evaluation/run_eval.py --limit 5 --strategies auto cheapest strongest
```

The evaluator uses `SMARTROUTE_API_URL` to select the gateway URL (default `http://127.0.0.1:8000`). Judging requires `GROQ_API_KEY`; `GROQ_BASE_URL` and `JUDGE_MODEL` configure its endpoint and model. Set `EVAL_REQUEST_DELAY_SECONDS` to adjust the delay between gateway requests.

Generated reports are written to `evaluation/results/detail.csv` and `evaluation/results/summary.csv`. These local evaluation outputs are Git-ignored. Evaluation makes external provider requests and can incur usage charges; start with a small `--limit`, consider `--no-judge`, and review the configured models and rates first.

When interpreting results, compare quality, cost, latency, route accuracy, and errors together. Choose a minimum acceptable quality score before claiming a cost reduction; the cheapest fixed-tier strategy is not necessarily good enough for a given task.

## Tests

Install the core requirements and run:

```bash
python -m pytest -q
```

The current automated tests cover the heuristic router's simple, medium, hard, and long-prompt classifications. They do not validate live provider behavior or guarantee the quality of generated answers.

## Data, privacy, and security notes

- Request prompts and generated answers are stored in the local SQLite request log; exact-cache entries also store answers. Treat the database as sensitive application data.
- The database, local environment files, virtual environment, test cache, and generated evaluation CSVs are excluded by `.gitignore`. Do not remove these exclusions without checking what the files contain.
- Do not commit provider credentials. Keep them in a private local `.env` file or a proper secret manager; `.env.example` is the safe template.
- `API_KEY` is optional and is one shared key, not a full user identity or authorization system. The caller-supplied `X-Tenant-ID` is not authentication.
- The rate limiter and circuit breaker are in-process and reset when the service restarts. They are not distributed across workers or hosts.
- The dashboard is intended for local use. The current service does not provide production-grade transport security, identity management, tenant authorization, audit controls, or PII redaction.
- Avoid sending sensitive prompts to external model providers unless you have reviewed their terms and data-handling settings.

## Troubleshooting

- **Provider is not configured:** add a valid key for the selected `PRIMARY_PROVIDER` to `.env`; verify the provider name and model ID.
- **Provider/model errors:** check that the model is currently available to your account, then review the configured provider base URL and fallback.
- **Dashboard cannot reach the API:** start Uvicorn in a separate terminal and verify the API URL and port.
- **Database appears empty or differs between processes:** start both processes from the project root and ensure they use the same `DATABASE_PATH`.
- **Semantic caching fails to initialize:** confirm the optional dependencies are installed and allow the embedding model to download; otherwise leave semantic caching disabled.
- **Evaluation takes a long time or hits rate limits:** lower `--limit`, use `--no-judge`, adjust `EVAL_REQUEST_DELAY_SECONDS`, and review provider rate limits.

## Known limitations

- The routing heuristic is keyword/length based and should be treated as an experimental policy.
- Model tiers and prices are manually configured; provider model quality and pricing can change.
- LLM-as-a-judge scores can be inconsistent or biased. Review samples with human judgment.
- Cost, cache-hit, and latency measurements are simplified and should not be treated as production telemetry.
- SQLite and in-memory state are suitable for a local demonstration, not high-concurrency or multi-instance deployment.
- The project has limited automated test coverage and no deployment, migration, or distributed-state management workflow.

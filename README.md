# Autonomous Data Governance Assistant

An agentic data-quality and governance platform built with FastAPI. A small
team of LLM-powered agents collaborates to **discover, profile, classify,
generate DQ rules, execute them, and trend the results** across multiple
data snapshots — all served behind a single FastAPI app with rich Swagger UI.

The reference dataset is a synthetic mortgage / home-loan SQLite database
(`branches`, `loan_officers`, `customers`, `applications`, `loans`,
`collaterals`, `payments`, `credit_history`) that supports multi-snapshot
loading so you can analyse data quality drift over time.

---

## Hackathon quickstart

The platform is designed to satisfy the agentathon non-negotiable
constraints: a single command boots a service on port 8000 that exposes a
single `POST /run` endpoint, auto-loads the bundled sample dataset, and
executes the entire agent pipeline end-to-end.

```bash
# 1. Install dependencies (CPU-only, no GPU required)
pip install -r requirements.txt

# 2. Provide your Compass API key. Either:
#    a) export COMPASS_API_KEY=...   (preferred for CI / organizers)
#    b) cp .env.example .env  and edit COMPASS_API_KEY=...
#    c) for local dev: keep MODE=local and put the key in `.env.local`

# 3. Boot the service on port 8000
python run.py

# 4. From another terminal, run the pipeline end-to-end (no manual setup)
curl -X POST http://localhost:8000/run \
     -H "Content-Type: application/json" \
     -d '{"db_name":"mortgage_demo","snapshot_date":"2025-01-01"}'
```

Sample payloads live under [input_examples/](input_examples/) and
[output_examples/](output_examples/) (3 inputs + 3 outputs + a bonus trend
example). Submission metadata is declared in [metadata.json](metadata.json).

### Run with Docker (recommended)

```bash
docker build -t agentathon .
docker run --rm -p 8000:8000 -e COMPASS_API_KEY=your-key agentathon
```

### Submission constraints — compliance map

| Constraint | Where it's met |
|---|---|
| Compass API integration | [app/utils/llm_client.py](app/utils/llm_client.py) (OpenAI client pointed at `https://api.core42.ai/v1`) |
| `run.py` + `POST /run` on port 8000 | [run.py](run.py), [app/main.py](app/main.py) |
| Runtime ≤ 15 min | discovery + profiling parallelised in [app/agents/orchestrator.py](app/agents/orchestrator.py) |
| Static data ≤ 500 MB | bundled sample DB regenerated on demand by `create_mortgage_database`; total repo well under cap |
| No API keys committed | `.env` is gitignored; real keys go in `.env.local` (also gitignored) |
| `.env.example` for organizers | [.env.example](.env.example) |
| Logs saved | [logs/](logs/) (per-agent + access + app, rotating) |
| ≥3 input + ≥3 output examples | [input_examples/](input_examples/), [output_examples/](output_examples/) |
| `metadata.json` | [metadata.json](metadata.json) |
| `Dockerfile` + `entrypoint.sh` | [Dockerfile](Dockerfile), [entrypoint.sh](entrypoint.sh) |
| CPU only | pure-Python stack (FastAPI + sqlite3 + OpenAI HTTP client) |
| Automated data loading | `POST /run` calls `setup_database=True` which invokes `create_mortgage_database` automatically |

---

## Features

- **Snapshot-aware data model** — every fact table carries a `report_date`
  column. The same database can hold many snapshots side-by-side; agents and
  endpoints always operate on a `(db_name, snapshot_date)` pair.
- **Multi-agent pipeline** orchestrated end-to-end via `/api/v1/pipeline/run`:
  - `connection_agent` — connectivity smoke test
  - `discovery_agent` — technical catalogue (tables, columns, FKs) **(runs in parallel with profiling)**
  - `profiling_agent` — column-level profiling + business glossary **(runs in parallel with discovery)**
  - `classification_agent` — PII / sensitivity classification
  - `dq_rules_agent` — generate DQ rules from catalogue + glossary
  - `dq_executor_agent` — run rules against the snapshot, score by
    dimension (Accuracy, Completeness, Consistency, Timeliness, Validity,
    Uniqueness)
  - `qa_agent` — natural-language Q&A scoped to a `(db, snapshot, table)`
- **Trend analysis** — `/api/v1/dq-scores/trend` summarises DQ-score movement
  across a date range using GPT-5.1 (overall, per-dimension, per-table,
  findings, risks, recommendations).
- **Per-snapshot, per-database isolation** — artifacts are persisted in a
  central `dq_admin.db` registry keyed on `(db_name, snapshot_date, kind)`
  with UPSERT semantics: re-running an agent for the same snapshot
  overwrites that snapshot's artifact; a new snapshot date appends.
- **Rich Swagger UI** with cascading dropdowns: `db_name` filters the
  `snapshot_date` / `snapshot_date_start` / `snapshot_date_end` selects to
  the snapshots that exist for the chosen database.
- **Per-agent log files** under `app/logs/agents/<agent>.log`, plus a unified
  `app.log` and an `api_access.log` for every HTTP request.
- **Two-mode secrets handling** — `.env` is the committed template with a
  `<COMPASS_API_KEY>` placeholder; real secrets live in a gitignored
  `.env.local` and are loaded automatically when `MODE=local`.

---

## Project structure

```
agentathon/
├── app/
│   ├── main.py                       # FastAPI app + custom Swagger UI
│   ├── agents/                       # LLM-driven agents
│   │   ├── orchestrator.py
│   │   ├── connection_agent.py
│   │   ├── discovery_agent.py
│   │   ├── profiling_agent.py
│   │   ├── classification_agent.py
│   │   ├── dq_rules_agent.py
│   │   ├── dq_executor_agent.py
│   │   └── qa_agent.py
│   ├── api/routes/                   # FastAPI routers (one per concern)
│   │   ├── database.py
│   │   ├── connection.py
│   │   ├── discovery.py
│   │   ├── profiling.py
│   │   ├── classification.py
│   │   ├── dq_rules.py
│   │   ├── dq_scores.py              # incl. /trend (GPT-5.1)
│   │   └── pipeline.py
│   ├── config/
│   │   ├── settings.py               # Pydantic settings, MODE-aware env loader
│   │   └── connections.yaml
│   ├── database/
│   │   ├── setup_mortgage_sample_db.py   # default sample loader
│   │   └── setup_sample_db.py            # legacy e-commerce loader
│   ├── models/                       # Pydantic schemas (catalogue, dq_rules, …)
│   ├── utils/
│   │   ├── db_registry.py            # dq_admin.db: DBs, snapshots, artifacts
│   │   ├── db_utils.py               # snapshot-aware SQL helpers
│   │   ├── llm_client.py             # Compass API wrapper (GPT-4.1 / GPT-5.1)
│   │   ├── logging_config.py         # rotating file handlers per agent
│   │   └── prompts.py
│   └── outputs/                      # generated JSON/MD artifacts
├── input_examples/                   # ≥3 sample request payloads
│   ├── input_1_run.json
│   ├── input_2_pipeline_run.json
│   └── input_3_qa_ask.json
├── output_examples/                  # ≥3 sample response payloads (+ trend)
│   ├── output_1_run.json
│   ├── output_2_pipeline_run.json
│   ├── output_3_qa_ask.json
│   └── output_4_trend.json
├── logs/                             # rotating log files (gitignored)
│   ├── app.log
│   ├── api_access.log
│   └── agents/<agent>.log
├── run.py                            # mandatory entry point → :8000
├── Dockerfile                        # CPU-only container image
├── entrypoint.sh                     # container entrypoint
├── metadata.json                     # mandatory submission metadata
├── requirements.txt
├── .env.example                      # template for organizers / CI (no secrets)
├── .env.local                        # real secrets (gitignored, local only)
└── PLAN.md
```

---

## Prerequisites

- Python 3.11+
- Windows / macOS / Linux
- A Compass API key (Core42) for LLM access

---

## Setup

```powershell
# 1. Clone and enter the repo
cd agentathon

# 2. Create + activate venv
python -m venv .venv
.\.venv\Scripts\Activate.ps1     # PowerShell
# source .venv/bin/activate      # bash

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure secrets
#    .env is committed with placeholders + MODE=local
#    Copy and fill in your real key:
Copy-Item .env .env.local
# Edit .env.local and set COMPASS_API_KEY=<your real key>
```

`.env.local` is gitignored and overrides `.env` whenever `MODE=local` (the
default). To deploy with the real key set in `.env`, change `MODE=prod` and
put the real key there.

---

## Running

```powershell
# Start the API (default: http://127.0.0.1:8000)
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Open Swagger UI:

- http://127.0.0.1:8000/docs  — interactive UI with cascading dropdowns
- http://127.0.0.1:8000/redoc — alternative reference

---

## Typical workflow

1. **Load a snapshot** (creates the SQLite file on first call):
   ```http
   POST /api/v1/database/setup
   {
     "db_name": "mortgage_demo",
     "snapshot_date": "2025-01-01"
   }
   ```
   Re-call with a new `snapshot_date` to append; same `(db, snapshot)`
   replaces only that snapshot's rows + clears its artifacts.

2. **Run the full pipeline** for that snapshot:
   ```http
   POST /api/v1/pipeline/run
   {
     "db_name": "mortgage_demo",
     "snapshot_date": "2025-01-01"
   }
   ```
   This runs connection → (discovery ∥ profiling) → classification →
   DQ rule generation → DQ rule execution and persists every artifact under
   `(db_name, snapshot_date, kind)`. Discovery and profiling are dispatched
   on a `ThreadPoolExecutor` because they read directly from the source
   database and have no inter-dependency.

3. **Inspect results**:
   - `GET /api/v1/discovery/catalogue?db_name=mortgage_demo&snapshot_date=2025-01-01`
   - `GET /api/v1/profiling/glossary?db_name=…&snapshot_date=…`
   - `GET /api/v1/classification/report?db_name=…&snapshot_date=…`
   - `GET /api/v1/dq-rules/rules?db_name=…&snapshot_date=…`
   - `GET /api/v1/dq-scores/results?db_name=…&snapshot_date=…`
   - `GET /api/v1/dq-scores/report?db_name=…&snapshot_date=…` (markdown)

4. **Ask a scoped question** about a table/column:
   ```http
   POST /api/v1/dq-scores/ask?db_name=mortgage_demo&snapshot_date=2025-01-01
   {
     "table_name": "customers",
     "column_name": "credit_score",
     "question": "What does the distribution look like and any concerns?"
   }
   ```

5. **Trend analysis across snapshots** (≥ 2 snapshots required):
   ```http
   GET /api/v1/dq-scores/trend
       ?db_name=mortgage_demo
       &snapshot_date_start=2025-01-01
       &snapshot_date_end=2025-04-01
   ```
   Returns `summary`, `overall_trend`, `key_findings`, `risks`,
   `recommendations`, `dimension_trends`, `table_trends`. Uses **GPT-5.1**.

---

## Sample data

The default loader is `app/database/setup_mortgage_sample_db.py`. It seeds:

| Table            | Notes                                                  |
|------------------|--------------------------------------------------------|
| `branches`       | 7 branches across US cities                            |
| `loan_officers`  | ~25 officers per snapshot                              |
| `customers`      | ~250 with PII (name, dob, age, gender, income, score)  |
| `applications`   | 400 applications with decisions / reasons              |
| `loans`          | ~260 booked loans (type, amount, rate, term, status)   |
| `collaterals`    | property pledged per loan, LTV, appraisals             |
| `payments`       | up to 24 months of amortisation per loan               |
| `credit_history` | 1-3 bureau pulls per customer                          |

Numbers (loan amounts, rates, credit scores, payment statuses) are seeded
deterministically from the snapshot date, so replays are stable but
different snapshot dates show genuine drift in totals and DQ patterns.

To load a snapshot from the CLI directly:

```powershell
python -m app.database.setup_mortgage_sample_db --db-name mortgage_demo --snapshot-date 2025-01-01
python -m app.database.setup_mortgage_sample_db --db-name mortgage_demo --snapshot-date 2025-04-01
```

---

## Architecture

### Snapshot semantics

Every data table carries `report_date TEXT NOT NULL`. Natural-key
uniqueness is enforced as `UNIQUE(<key>, report_date)` so the same logical
entity (e.g. customer email) can appear in multiple snapshots while staying
unique within each snapshot.

```
mortgage_demo.db
├── customers   (report_date='2025-01-01')  ← snapshot A rows
├── customers   (report_date='2025-04-01')  ← snapshot B rows
├── loans       (report_date='2025-01-01')
├── loans       (report_date='2025-04-01')
└── …
```

### Artifact persistence

A central `app/database/dq_admin.db` registry tracks:

- `dq_admin_databases` — registered DBs and their paths
- `dq_admin_snapshots(db_name, snapshot_date)` — known snapshots per DB
- `dq_admin_artifacts(db_name, snapshot_date, kind, payload_json)` — JSON
  artifacts (technical_catalogue, data_glossary, classification_report,
  dq_rules, dq_scores) with **UPSERT** so re-runs replace, never duplicate
- `dq_admin_dq_report(db_name, snapshot_date, markdown)` — markdown report

### LLM models

- **GPT-4.1** — default for catalogue, glossary, classification, rule
  generation, and Q&A.
- **GPT-5.1** — used for complex reasoning: `/dq-scores/trend`.

Configured in `app/utils/llm_client.py`; switch via `use_complex_model=True`.

---

## Logging

`app/utils/logging_config.py` configures three sinks (all rotating, 5 MB × 5):

- `app/logs/app.log` — every log record across the app
- `app/logs/api_access.log` — one line per HTTP request
- `app/logs/agents/<agent>.log` — per-agent file (records also propagate
  to `app.log` for a unified view)

Set `LOG_LEVEL` in your `.env` / `.env.local` to control verbosity.

---

## Running the existing test

A simple Compass API smoke test is included:

```powershell
.\.venv\Scripts\python.exe test_compass_api.py
```

---

## Common operations

```powershell
# List registered DBs and snapshots
curl http://127.0.0.1:8000/api/v1/database/list
curl http://127.0.0.1:8000/api/v1/database/snapshots
curl http://127.0.0.1:8000/api/v1/database/snapshot-map

# Inspect outputs on disk
ls app/outputs/<db_name>/

# Tail an agent's log
Get-Content app/logs/agents/dq_executor_agent.log -Tail 50 -Wait
```

---

## Notes

- Re-running any agent endpoint for the same `(db_name, snapshot_date)`
  overwrites that snapshot's artifact in place. A different `snapshot_date`
  always appends a new row, so historical analyses stay intact.
- If you have a stale `"string"` placeholder snapshot from early experiments,
  remove it with:
  ```powershell
  .\.venv\Scripts\python.exe -c "import sqlite3; c=sqlite3.connect('app/database/dq_admin.db'); c.execute(\"DELETE FROM dq_admin_snapshots WHERE snapshot_date='string'\"); c.commit(); print('cleaned')"
  ```
- The legacy e-commerce loader (`app/database/setup_sample_db.py`) is still
  importable and runnable directly if you want a different sample dataset.

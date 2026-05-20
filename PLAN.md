# Autonomous Metadata & Data Insights Research Assistant

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Orchestrator Agent                            │
│         (Coordinates all steps, manages state & workflow)            │
└──────────┬──────────┬──────────┬──────────┬──────────┬─────────────┘
           │          │          │          │          │
    ┌──────▼──┐ ┌─────▼────┐ ┌──▼───┐ ┌───▼────┐ ┌──▼──────────┐
    │Connection│ │Discovery │ │Profile│ │Classify│ │Data Quality │
    │  Agent   │ │  Agent   │ │Agent  │ │ Agent  │ │   Agent     │
    └──────────┘ └──────────┘ └──────┘ └────────┘ └─────────────┘
                                                          │
                                                   ┌──────▼──────┐
                                                   │  DQ Executor │
                                                   │    Agent     │
                                                   └─────────────┘
```

---

## Step-by-Step Plan

### Step 1: Sample Database Creation (No AI Agent needed)

**Purpose:** Create a realistic SQLite database with multiple related tables, constraints, and sample data.

**Implementation:**
- Script: `app/database/setup_sample_db.py`
- Database: `app/database/sample.db`
- Tables (suggested domain: E-Commerce / Retail):
  - `customers` - customer demographics
  - `products` - product catalog
  - `orders` - order headers
  - `order_items` - order line items
  - `suppliers` - supplier information
  - `categories` - product categories
  - `employees` - internal staff
  - `payments` - payment transactions
  - `shipping` - shipping records
  - `reviews` - product reviews

**Constraints to include:**
- Primary keys on all tables
- Foreign keys (orders → customers, order_items → orders/products, etc.)
- NOT NULL on critical columns
- UNIQUE constraints (email, phone, SKU)
- CHECK constraints (price > 0, rating between 1-5)
- DEFAULT values

**Data characteristics (to make DQ interesting):**
- ~500-1000 rows per main table
- Intentionally introduce some quality issues:
  - Missing values in non-critical fields
  - Some duplicate entries
  - Inconsistent formats (dates, phone numbers)
  - Outlier values
  - Stale/old records for timeliness checks

**AI Agent: NOT NEEDED** — This is deterministic setup code.

---

### Step 2: Connection Agent

**Purpose:** Validate database connectivity given credentials.

**Implementation:**
- Module: `app/agents/connection_agent.py`
- Config: `app/config/connections.yaml`

**Logic:**
1. Accept connection parameters (db_type, host, port, database, user, password)
2. For SQLite: validate file exists and is readable
3. For other DBs: attempt connection with timeout
4. Return structured result: `{status: "success"|"error", message: str, metadata: {...}}`

**AI Agent: MINIMAL** — Connection logic is deterministic, but an AI agent can:
- Interpret error messages and suggest fixes
- Auto-detect database type from connection string patterns
- Provide human-readable diagnostics

---

### Step 3: Discovery Agent (Technical Catalogue) 🤖 AI AGENT

**Purpose:** Extract and organize all metadata into a structured technical catalogue.

**Implementation:**
- Module: `app/agents/discovery_agent.py`
- Output: `app/outputs/technical_catalogue.json`

**Process:**
1. Query `sqlite_master` for all tables and views
2. Query `PRAGMA table_info(table)` for columns, types, defaults, NOT NULL
3. Query `PRAGMA foreign_key_list(table)` for relationships
4. Query `PRAGMA index_list(table)` and `PRAGMA index_info(index)` for indexes/unique constraints
5. Build a structured catalogue with:
   - Table metadata (name, row count, column count)
   - Column metadata (name, type, nullable, default, constraints)
   - Relationship map (FK references)
   - Constraint inventory

**AI Agent: RECOMMENDED** for:
- Generating human-readable descriptions of tables and relationships
- Inferring table purpose from column names and relationships
- Identifying data model patterns (star schema, normalized, etc.)
- Creating an ER diagram description

---

### Step 4: Data Profiling Agent 🤖 AI AGENT (Critical)

**Purpose:** Profile data statistically and generate business-meaningful descriptions.

**Implementation:**
- Module: `app/agents/profiling_agent.py`
- Output: `app/outputs/data_glossary.json`

**Process:**
1. **Statistical Profiling (deterministic):**
   - Numeric columns: min, max, mean, median, std_dev, percentiles, null_count, zero_count
   - String columns: min_length, max_length, avg_length, pattern analysis, top_n values
   - Date columns: min_date, max_date, range, null_count
   - All columns: distinct_count, null_percentage, completeness_ratio

2. **AI-Driven Analysis:**
   - Infer business descriptions for each column based on:
     - Column name semantics
     - Data type and constraints
     - Sample values (top 10-20 distinct values)
     - Statistical profile
     - Table context and relationships
   - Identify enumeration columns (low cardinality) and list valid values
   - Detect potential PII fields
   - Generate a business glossary entry for each column

**AI Agent: ESSENTIAL** — The LLM generates:
- Business descriptions (e.g., `customer_id` → "Unique identifier for each customer in the system")
- Data domain classification (e.g., "This appears to be an email address field")
- Value interpretation (e.g., status codes → meaningful labels)
- Relationship context (e.g., "Links to the parent order record")

---

### Step 5: Classification & CDE Agent 🤖 AI AGENT (Critical)

**Purpose:** Classify data sensitivity and identify Critical Data Elements.

**Implementation:**
- Module: `app/agents/classification_agent.py`
- Output: `app/outputs/classification_report.json`

**Classification Levels:**
| Level | Description | Examples |
|-------|-------------|----------|
| Public | No business impact if disclosed | Product names, categories |
| Internal | Low impact, internal use only | Order counts, internal IDs |
| Confidential | Medium impact, business sensitive | Revenue, pricing strategies |
| Restricted | High impact, regulated data | PII, payment info, SSN |

**CDE Identification Criteria (AI-driven):**
- Business impact: Would errors in this field affect decisions?
- Regulatory relevance: Is this field subject to compliance?
- Financial impact: Does this field affect revenue/cost calculations?
- Customer impact: Does this field directly affect customer experience?
- Downstream dependencies: How many processes consume this field?

**AI Agent: ESSENTIAL** — The LLM:
- Classifies each column into Public/Internal/Confidential/Restricted based on:
  - Column name semantics
  - Sample data inspection
  - Table context
  - Common data classification frameworks (GDPR, PCI-DSS patterns)
- Selects ~20% of columns as CDE with justification
- Provides rationale for each classification decision

---

### Step 6: Data Quality Rules Agent 🤖 AI AGENT (Critical)

**Purpose:** Generate executable DQ rules mapped to quality dimensions.

**Implementation:**
- Module: `app/agents/dq_rules_agent.py`
- Output: `app/outputs/dq_rules.json`

**Six Dimensions of Data Quality:**

| Dimension | Description | Example Rules |
|-----------|-------------|---------------|
| **Accuracy** | Data correctly represents real-world | Email format validation, range checks |
| **Completeness** | Required data is present | NOT NULL checks on critical fields, mandatory field checks |
| **Consistency** | Data agrees across systems/records | Status values match allowed set, cross-table integrity |
| **Timeliness** | Data is current and up-to-date | Records updated within expected timeframe, no stale data |
| **Validity** | Data conforms to defined formats/rules | Date formats, enum values, regex patterns |
| **Uniqueness** | No unintended duplicates exist | Unique email, no duplicate orders, key uniqueness |

**Rule Structure:**
```json
{
  "rule_id": "DQ_001",
  "rule_name": "Customer Email Format Valid",
  "dimension": "Validity",
  "table": "customers",
  "column": "email",
  "rule_type": "technical|business",
  "description": "All customer emails must match standard email format",
  "sql_query": "SELECT COUNT(*) as failures FROM customers WHERE email NOT LIKE '%_@_%.__%'",
  "threshold": 0.95,
  "severity": "high",
  "cde_linked": true
}
```

**AI Agent: ESSENTIAL** — The LLM generates:
- Technical rules (format validations, null checks, range checks)
- Business rules (logical consistency, cross-field validation, temporal rules)
- Maps each rule to appropriate DQ dimension
- Creates executable SQL for each rule
- Sets appropriate thresholds based on column criticality (stricter for CDE)
- Prioritizes CDE columns for business rules

---

### Step 7: DQ Execution & Scoring Agent

**Purpose:** Execute all rules, compute scores, and produce consolidated report.

**Implementation:**
- Module: `app/agents/dq_executor_agent.py`
- Output: `app/outputs/dq_scores.json` + `app/outputs/dq_report.md`

**Scoring Methodology:**
```
Rule Score = (total_records - failed_records) / total_records × 100

Dimension Score = Weighted average of rule scores in that dimension
  (CDE rules get 2x weight)

Table Score = Average of all 6 dimension scores for that table

Database Score = Weighted average of table scores
  (Weight by row count or business importance)
```

**Output Structure:**
```
Database Level:  Overall DQ Score = X%
  ├── Table: customers (Score: Y%)
  │     ├── Accuracy:    Z%
  │     ├── Completeness: Z%
  │     ├── Consistency:  Z%
  │     ├── Timeliness:   Z%
  │     ├── Validity:     Z%
  │     └── Uniqueness:   Z%
  ├── Table: orders (Score: Y%)
  │     └── ...
  └── ...
```

**AI Agent: RECOMMENDED** for:
- Interpreting results and generating narrative insights
- Identifying root causes of quality issues
- Suggesting remediation actions
- Prioritizing fixes by business impact
- Generating executive summary

---

## Technology Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.11+ |
| API Framework | FastAPI (REST endpoints for all agents & results) |
| Database | SQLite (sample), extensible to PostgreSQL/MySQL |
| AI/LLM | OpenAI GPT-4 / Azure OpenAI (via API) |
| Agent Framework | Custom lightweight agent loop |
| Configuration | YAML + environment variables |
| Output Formats | JSON (structured) + Markdown (reports) |
| Orchestration | FastAPI background tasks + sequential pipeline |

---

## REST API Endpoints (FastAPI)

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/api/v1/database/setup` | Create/reset sample database |
| POST | `/api/v1/connection/test` | Test database connectivity |
| POST | `/api/v1/discovery/run` | Run discovery agent → technical catalogue |
| GET | `/api/v1/discovery/results` | View technical catalogue |
| POST | `/api/v1/profiling/run` | Run profiling agent → data glossary |
| GET | `/api/v1/profiling/results` | View data glossary |
| POST | `/api/v1/classification/run` | Run classification agent → CDE report |
| GET | `/api/v1/classification/results` | View classification report |
| POST | `/api/v1/dq-rules/generate` | Run DQ rules agent → generate rules |
| GET | `/api/v1/dq-rules/results` | View generated DQ rules |
| POST | `/api/v1/dq-rules/execute` | Execute DQ rules → scores |
| GET | `/api/v1/dq-scores/results` | View DQ scores & report |
| POST | `/api/v1/pipeline/run` | Run full pipeline (all steps) |
| GET | `/api/v1/pipeline/status` | Check pipeline execution status |

---

## Project Structure

```
agentathon/
├── app/
│   ├── __init__.py
│   ├── main.py                     # FastAPI application entry point
│   ├── config/
│   │   ├── __init__.py
│   │   ├── connections.yaml        # DB connection configs
│   │   └── settings.py             # App settings
│   ├── api/
│   │   ├── __init__.py
│   │   └── routes/
│   │       ├── __init__.py
│   │       ├── database.py         # /api/v1/database/* endpoints
│   │       ├── connection.py       # /api/v1/connection/* endpoints
│   │       ├── discovery.py        # /api/v1/discovery/* endpoints
│   │       ├── profiling.py        # /api/v1/profiling/* endpoints
│   │       ├── classification.py   # /api/v1/classification/* endpoints
│   │       ├── dq_rules.py         # /api/v1/dq-rules/* endpoints
│   │       ├── dq_scores.py        # /api/v1/dq-scores/* endpoints
│   │       └── pipeline.py         # /api/v1/pipeline/* endpoints
│   ├── database/
│   │   ├── __init__.py
│   │   ├── setup_sample_db.py      # Creates sample SQLite DB
│   │   └── sample.db               # Generated database
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── orchestrator.py         # Main workflow coordinator
│   │   ├── connection_agent.py     # Step 2: Connection validation
│   │   ├── discovery_agent.py      # Step 3: Technical catalogue
│   │   ├── profiling_agent.py      # Step 4: Data profiling & glossary
│   │   ├── classification_agent.py # Step 5: Classification & CDE
│   │   ├── dq_rules_agent.py       # Step 6: DQ rule generation
│   │   └── dq_executor_agent.py    # Step 7: DQ execution & scoring
│   ├── models/
│   │   ├── __init__.py
│   │   ├── catalogue.py            # Data models for catalogue
│   │   ├── glossary.py             # Data models for glossary
│   │   ├── classification.py       # Data models for classification
│   │   └── dq_rules.py             # Data models for DQ rules
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── db_utils.py             # Database helper functions
│   │   ├── llm_client.py           # LLM API wrapper
│   │   └── prompts.py              # Prompt templates for agents
│   └── outputs/                    # Generated outputs (gitignored)
│       ├── technical_catalogue.json
│       ├── data_glossary.json
│       ├── classification_report.json
│       ├── dq_rules.json
│       ├── dq_scores.json
│       └── dq_report.md
├── requirements.txt
├── .env.example                    # Environment variable template
├── README.md
└── PLAN.md                         # This file
```

---

## AI Agent Usage Summary

| Step | Component | AI Agent? | AI Contribution |
|------|-----------|-----------|-----------------|
| 1 | Sample DB Setup | ❌ No | Deterministic script |
| 2 | Connection | ⚡ Minimal | Error interpretation only |
| 3 | Discovery | 🤖 Yes | Table/column descriptions, pattern recognition |
| 4 | Profiling | 🤖 **Critical** | Business descriptions, domain inference, glossary generation |
| 5 | Classification | 🤖 **Critical** | Sensitivity classification, CDE identification with rationale |
| 6 | DQ Rules | 🤖 **Critical** | Full rule generation including SQL, thresholds, dimension mapping |
| 7 | DQ Execution | 🤖 Yes | Result interpretation, insights, remediation suggestions |

---

## Agent Design Principles

1. **Structured I/O:** Each agent receives structured input (JSON) and produces structured output (JSON). LLM responses are parsed into Pydantic models.

2. **Deterministic + AI Hybrid:** Statistical computations (profiling, scoring) are deterministic. Interpretation and generation are AI-driven.

3. **Prompt Engineering:** Each agent has carefully crafted system prompts with:
   - Role definition
   - Input schema description
   - Output schema with examples
   - Domain knowledge (DQ dimensions, classification frameworks)
   - Constraints (e.g., "select exactly 20% as CDE")

4. **Validation Layer:** AI-generated outputs (especially SQL rules) are validated before execution to prevent injection or errors.

5. **Idempotent & Resumable:** Each step saves output to disk. Pipeline can resume from any step.

6. **Observability:** Each agent logs its reasoning, decisions, and confidence levels.

---

## Execution Flow

```
# Start the FastAPI server
uvicorn app.main:app --reload --port 8000

# API calls (via curl, Swagger UI at /docs, or any HTTP client):
POST /api/v1/database/setup         → Creates sample.db
POST /api/v1/connection/test        → Validates connectivity
POST /api/v1/discovery/run          → Builds technical catalogue
POST /api/v1/profiling/run          → Creates data glossary
POST /api/v1/classification/run     → Classifies & identifies CDEs
POST /api/v1/dq-rules/generate      → Generates DQ rules
POST /api/v1/dq-rules/execute       → Executes rules & produces scores
POST /api/v1/pipeline/run           → Runs all steps end-to-end
```

---

## Next Steps

1. ✅ Plan created (this document)
2. ⬜ Set up project structure and dependencies
3. ⬜ Implement Step 1: Sample database creation
4. ⬜ Implement Step 2: Connection agent
5. ⬜ Implement Step 3: Discovery agent
6. ⬜ Implement Step 4: Profiling agent
7. ⬜ Implement Step 5: Classification agent
8. ⬜ Implement Step 6: DQ rules agent
9. ⬜ Implement Step 7: DQ executor agent
10. ⬜ Implement orchestrator and end-to-end pipeline
11. ⬜ Test and validate full workflow

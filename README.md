# db-analytics

A conversational data warehouse workflow for [Mistral Vibe Work](https://work.mistral.ai). Ask business questions in natural language — the system discovers the relevant schema via [SLayer](https://github.com/MotleyAI/slayer), queries a local SQLite warehouse, and returns insights.

## Architecture

```
Vibe Work (cloud UI)
  └─ Mistral Orchestrator (wf-scheduler.mistral.ai)
       └─ Local Worker (your machine)
            │
            ├─ 1. discover_context     ← SLayer search + inspect
            │     Finds relevant models/columns for the question
            │
            ├─ 2. generate_query_plan  ← Mistral LLM
            │     Generates a SlayerQuery from discovered context
            │
            ├─ 3. execute_warehouse_query  ← SLayer engine
            │     Translates SlayerQuery → SQL → SQLite → JSON rows
            │
            └─ 4. analyze_results      ← Mistral LLM
                  Produces a markdown report with insights
```

### Search → Inspect → Query Pattern

Instead of sending the entire database schema to the LLM (which doesn't scale beyond a handful of tables), we use SLayer's search-then-inspect approach:

1. **Search** — SLayer semantically searches its model index for columns, tables, and joins relevant to the user's question (e.g., "revenue by region" → `fact_order.revenue`, `dim_region.region_name`)
2. **Inspect** — only the matched models are inspected in detail, producing a compact schema context
3. **Query** — the LLM sees only the relevant schema and generates a precise `SlayerQuery`
4. **Execute** — SLayer handles SQL generation, joins, and execution

This keeps the LLM context small and focused, even with thousands of tables.

## Project Structure

```
db-analytics/
├── .env.example              # Template for environment variables
├── Makefile                   # Common commands
├── pyproject.toml             # Python dependencies
├── schema.sql                 # DDL for the star-schema warehouse
├── generate_data.py           # Generates 5,000 synthetic orders
├── warehouse.db               # SQLite database (generated)
└── src/
    ├── discover.py            # Worker entrypoint — auto-discovers workflows
    ├── start.py               # CLI trigger helper
    ├── slayer_setup.py        # SLayer initialization (engine, search, inspect)
    └── workflows/
        ├── activities.py      # Activities (outside Temporal sandbox)
        └── data_query.py      # Workflow class (inside Temporal sandbox)
```

## Data Model

Star schema with 5,000 synthetic orders spanning Jan 2023 – Dec 2024:

| Table | Description |
|---|---|
| `fact_order` | Order lines with revenue, cost, profit, quantity |
| `dim_date` | Calendar dimension (year, month, quarter, day) |
| `dim_customer` | 10 customers with segments and lifecycle status |
| `dim_product` | 10 products across Electronics, Furniture, Stationery |
| `dim_region` | 5 regions: North America, Europe, Asia Pacific, Latin America, Africa |

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager
- A [Mistral API key](https://console.mistral.ai/)

## Setup

```bash
# Clone the repo
git clone https://github.com/vinitshetty/db-analytics.git
cd db-analytics

# Install dependencies
uv sync

# Configure environment
cp .env.example .env
# Edit .env and add your MISTRAL_API_KEY

# Generate the data warehouse
make generate-data
```

## Usage

### Start the local worker

Keep this running in a terminal — it connects to the Mistral orchestrator and processes workflow executions:

```bash
make start-worker
```

You should see:
```
Discovered 1 workflow(s):
  - DataWarehouseQueryWorkflow

Starting worker – connected to Mistral orchestrator ...
```

### Use in Vibe Work

1. Open [Vibe Work](https://work.mistral.ai)
2. Click the **+** menu
3. Select **Data Warehouse Query**
4. Ask a question like:
   - "What is our total revenue?"
   - "Show revenue by region"
   - "Who are our top 5 customers?"
   - "Monthly revenue trend"
   - "Profit by product category"

### Trigger via CLI

```bash
make execute workflow=data-warehouse-query input='{}'
```

## How It Works — Detailed Walkthrough

For the question **"Show revenue by region"**, here's exactly what happens at each step:

### Step 1 — `discover_context` (SLayer — no LLM)

SLayer's `SearchService` searches its model index for columns, tables, and joins relevant to the question:

```
SearchService.search(question="Show revenue by region", max_results=10)

Search hits:
  column:  warehouse.fact_order.revenue      (score=0.0164)
  column:  warehouse.dim_region.region_name  (score=0.0161)
  model:   warehouse.fact_order              (score=0.0159)
  model:   warehouse.dim_region              (score=0.0156)
  column:  warehouse.dim_customer.region     (score=0.0154)
  ...

Unique models found: [dim_region, fact_order]
```

Then `InspectService` fetches detailed schema for **only the matched models** (not the whole database):

```
InspectService.inspect(reference="fact_order", entity_type="model")
InspectService.inspect(reference="dim_region", entity_type="model")
```

This produces ~3K chars of targeted context:

```markdown
# Model: `fact_order`
| name | type |
| revenue | DOUBLE |
| cost | DOUBLE |
| profit | DOUBLE |
| order_status | TEXT |
| region_id | INT |
...
Joins to: dim_region (region_id = region_id)

# Model: `dim_region`
| name | type |
| region_name | TEXT |
| country | TEXT |
| continent | TEXT |
...
Joins to: fact_order (region_id = region_id)
```

With 1,000s of tables, only the relevant ones are inspected — the LLM never sees the rest.

### Step 2 — `generate_query_plan` (Mistral LLM call #1)

The discovered context is injected into a system prompt that teaches the LLM the `SlayerQuery` format:

```
SYSTEM PROMPT:
  You are a data analyst. You have access to a semantic layer (SLayer)...

  [discovered schema context from Step 1]     ← what columns/joins exist

  === SLAYER QUERY FORMAT ===                  ← how to structure the output
  {
    "source_model": "<model_name>",
    "measures": ["sum(column)", "count(*)"],
    "dimensions": ["joined_model.column"],
    "filters": ["column = 'value'"],
    ...
  }

  === RULES ===                                ← business logic
  - Always filter to order_status = 'Completed' unless asked otherwise.

  Respond ONLY with a JSON object.

USER: Show revenue by region
```

The LLM's job is **slot-filling** — pick the right column names from the discovered schema and put them in the right fields. It outputs:

```json
{
  "query": {
    "source_model": "fact_order",
    "measures": ["sum(revenue)"],
    "dimensions": ["dim_region.region_name"],
    "filters": ["order_status = 'Completed'"]
  }
}
```

The LLM never writes SQL. It only selects measures, dimensions, and filters from the schema context.

The Mistral API is called with `response_format={"type": "json_object"}` to guarantee valid JSON output.

### Step 3 — `execute_warehouse_query` (SLayer — no LLM)

SLayer's `SlayerQueryEngine` takes the `SlayerQuery` and deterministically generates SQL:

```
SlayerQuery(                              SLayer engine (no LLM)
  source_model="fact_order",         ──►  SELECT dim_region.region_name,
  measures=["sum(revenue)"],                     SUM(fact_order.revenue) AS revenue_sum
  dimensions=["dim_region.          ──►  FROM fact_order
    region_name"],                        LEFT JOIN dim_region
  filters=["order_status                   ON fact_order.region_id = dim_region.region_id
    = 'Completed'"]                 ──►  WHERE fact_order.order_status = 'Completed'
)                                         GROUP BY dim_region.region_name
```

SLayer handles:
- **Join resolution** — knows `fact_order.region_id → dim_region.region_id` from auto-ingestion
- **SQL dialect** — generates SQLite SQL here, would generate Snowflake/Postgres SQL for other databases
- **Execution** — runs the query via SQLAlchemy and returns JSON rows

```json
[
  {"fact_order.dim_region.region_name": "Europe",        "fact_order.revenue_sum": 322299.29},
  {"fact_order.dim_region.region_name": "Asia Pacific",  "fact_order.revenue_sum": 299663.86},
  {"fact_order.dim_region.region_name": "Africa",        "fact_order.revenue_sum": 287448.56},
  {"fact_order.dim_region.region_name": "Latin America", "fact_order.revenue_sum": 279950.05},
  {"fact_order.dim_region.region_name": "North America", "fact_order.revenue_sum": 232923.36}
]
```

### Step 4 — `analyze_results` (Mistral LLM call #2)

The LLM receives the question, the query, and the raw JSON rows, and produces a human-friendly report:

```
Input to LLM:
  Question: "Show revenue by region"
  Query: {"source_model": "fact_order", "measures": ["sum(revenue)"], ...}
  Results: [{"region_name": "Europe", "revenue_sum": 322299.29}, ...]

Output from LLM:
  ## Revenue by Region

  | Region | Revenue |
  |---|---|
  | Europe | $322,299.29 |
  | Asia Pacific | $299,663.86 |
  | Africa | $287,448.56 |
  | Latin America | $279,950.05 |
  | North America | $232,923.36 |

  - Europe leads with 22.7% of total revenue
  - North America trails at 16.4%
  - Total revenue across all regions: $1,422,285.12
```

### What uses LLM vs. what doesn't

| Component | Uses LLM? | What it does |
|---|---|---|
| `ingest_datasource()` | No | Auto-discovers tables, columns, types, joins from the database |
| `SearchService.search()` | No | Keyword/embedding search over the model index |
| `InspectService.inspect()` | No | Renders detailed schema for specific models |
| `generate_query_plan()` | **Yes** (LLM call #1) | Natural language → structured `SlayerQuery` JSON |
| `SlayerQueryEngine.execute_sync()` | No | `SlayerQuery` → SQL → execute → JSON rows |
| `analyze_results()` | **Yes** (LLM call #2) | JSON rows → markdown report with insights |

**2 LLM calls per question.** Everything else is deterministic code. The LLM never writes SQL — it only picks columns and aggregations from the discovered schema. SLayer guarantees the SQL is valid, joins are correct, and the right dialect is used.

### Temporal Sandbox

Mistral Workflows use [Temporal](https://temporal.io/) for durable execution. The workflow class (`data_query.py`) runs inside a **deterministic sandbox** that restricts file I/O, network calls, and other side effects. All side-effectful work is done in **activities** (`activities.py`) which run outside the sandbox.

### SLayer Integration

[SLayer](https://github.com/MotleyAI/slayer) (motley-slayer) provides the semantic layer:

- **Auto-ingestion** — on worker startup, SLayer scans the database and auto-discovers all tables, columns, types, joins, and cardinalities
- **Search** — `SearchService.search()` finds relevant models and columns for a given question
- **Inspect** — `InspectService.inspect()` renders detailed schema for specific models
- **Query engine** — `SlayerQueryEngine` translates `SlayerQuery` objects into SQL, handles joins automatically, and executes against the database
- **Database support** — SQLite, PostgreSQL, MySQL, Snowflake, BigQuery, ClickHouse, SQL Server, Trino (via SQLAlchemy)

## Makefile Commands

| Command | Description |
|---|---|
| `make start-worker` | Start the local Temporal worker |
| `make execute workflow=... input=...` | Trigger a workflow from the CLI |
| `make generate-data` | Regenerate the SQLite warehouse with synthetic data |
| `make setup` | Install dependencies and show setup instructions |

## Quick Demo

Four commands to go from zero to a working demo:

```bash
# 1. Clone & install
git clone https://github.com/vinitshetty/db-analytics.git
cd db-analytics
uv sync

# 2. Configure (add your Mistral API key)
cp .env.example .env
# Edit .env → set MISTRAL_API_KEY=your-key-here

# 3. Generate the warehouse (5,000 synthetic orders)
make generate-data

# 4. Start the worker (keep this terminal open)
make start-worker
```

Then open [Vibe Work](https://work.mistral.ai) → click **+** → select **Data Warehouse Query** → ask a question.

You'll see 4 progress steps in the Vibe Work UI:

| Step | What happens |
|---|---|
| Discovering relevant schema | SLayer searches its model index for columns/tables matching your question |
| Building query plan | Mistral LLM generates a semantic query from the discovered context |
| Querying the warehouse | SLayer translates the query to SQL and executes against local SQLite |
| Analyzing results | Mistral LLM produces a markdown report with table and insights |

**Example questions to try:**
- "What is our total revenue?"
- "Show revenue by region"
- "Who are our top 5 customers by order count?"
- "Monthly revenue trend for 2024"
- "Profit by product category"
- "Average order value by customer segment"

## License

MIT

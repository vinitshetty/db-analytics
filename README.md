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
git clone https://github.com/vinut-shetty/db-analytics.git
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

## How It Works

### Temporal Sandbox

Mistral Workflows use [Temporal](https://temporal.io/) for durable execution. The workflow class (`data_query.py`) runs inside a **deterministic sandbox** that restricts file I/O, network calls, and other side effects. All side-effectful work is done in **activities** (`activities.py`) which run outside the sandbox.

### SLayer Integration

[SLayer](https://github.com/MotleyAI/slayer) (motley-slayer) provides the semantic layer:

- **Auto-ingestion** — on worker startup, SLayer scans `warehouse.db` and auto-discovers all tables, columns, types, joins, and cardinalities
- **Search** — `SearchService.search()` finds relevant models and columns for a given question using keyword matching
- **Inspect** — `InspectService.inspect()` renders detailed schema for specific models
- **Query engine** — `SlayerQueryEngine` translates `SlayerQuery` objects (measures, dimensions, filters) into SQL, handles joins automatically, and executes against the database

### Mistral Workflow Activities

| Activity | What it does |
|---|---|
| `discover_context` | Searches SLayer for relevant models/columns, inspects them, returns targeted schema context |
| `generate_query_plan` | Sends discovered context + question to Mistral LLM, gets back a `SlayerQuery` JSON |
| `execute_warehouse_query` | Passes the `SlayerQuery` to SLayer's engine for SQL generation and execution |
| `analyze_results` | Sends question + query + results to Mistral LLM for a human-friendly markdown report |

## Makefile Commands

| Command | Description |
|---|---|
| `make start-worker` | Start the local Temporal worker |
| `make execute workflow=... input=...` | Trigger a workflow from the CLI |
| `make generate-data` | Regenerate the SQLite warehouse with synthetic data |
| `make setup` | Install dependencies and show setup instructions |

## License

MIT

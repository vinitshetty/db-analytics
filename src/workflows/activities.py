"""
Activities for the data warehouse query workflow.

Activities run on the local worker OUTSIDE the Temporal sandbox, so they
can freely do file I/O, database queries, network calls, etc.

Uses the SLayer semantic layer library (motley-slayer) with a
search → inspect → query pattern for scalable schema discovery.
"""

import json
from datetime import timedelta

import mistralai.workflows as workflows
from mistralai.workflows import Depends
from mistralai.workflows.client import get_mistral_client

from slayer.async_utils import run_sync
from slayer.core.query import SlayerQuery

from src.slayer_setup import get_engine, get_inspect, get_search

# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------

QUERY_PLAN_SYSTEM = """\
You are a data analyst. You have access to a semantic layer (SLayer) over a
data warehouse. Below is the schema context discovered for this question:

{slayer_context}

=== SLAYER QUERY FORMAT ===
Produce a JSON object describing a SlayerQuery. The ONLY allowed fields are:

{{
  "source_model": "<model_name>",
  "measures": ["sum(column)", "count(*)"],
  "dimensions": ["joined_model.column"],
  "filters": ["column = 'value'"],
  "order": [{{"column": "column_sum", "direction": "desc"}}],
  "limit": 50,
  "time_dimensions": [{{"dimension": "col", "granularity": "month"}}]
}}

Allowed fields: source_model, measures, dimensions, filters, order, limit, time_dimensions.
DO NOT include any other fields (no "joins", no "group_by", no "select").
SLayer resolves joins automatically — you never specify them.

Field details:
- source_model: the main model to query (typically "fact_order")
- measures: aggregation expressions — sum(X), count(*), avg(X), min(X), max(X)
- dimensions: columns to group by; use dot notation for joins (e.g. "dim_region.region_name")
- filters: SQL-like filter expressions using ONLY columns from the schema above
- order: ordering spec; measure aliases use suffix: sum(X) → X_sum, count(*) → _count
- limit: max rows (default 50)
- time_dimensions: for time-series queries

=== CRITICAL RULES ===
- ONLY use column names, model names, and values that exist in the schema above.
- DO NOT invent columns, models, or values that are not listed.
- If the user asks about something not in the schema, respond with:
  {{"query": null, "reason": "The requested data is not available in the warehouse."}}
- Always filter to order_status = 'Completed' unless the user asks otherwise.
- Use round() in measures for monetary values: "round(sum(revenue), 2)"

Respond ONLY with a JSON object (no markdown, no explanation):
{{"query": {{...the SlayerQuery object...}}}}
"""

ANALYSIS_SYSTEM = """\
You are a senior business analyst. You will receive:
1. The user's original question.
2. The semantic query that was executed.
3. The result rows as JSON.

Produce a clear, concise answer:
- Lead with the direct answer.
- Include a markdown table if there are multiple rows.
- Add 2-3 bullet-point insights or observations.
- Keep it under 300 words.
"""


# ---------------------------------------------------------------------------
# Activities
# ---------------------------------------------------------------------------

@workflows.activity(
    name="discover_context",
    start_to_close_timeout=timedelta(seconds=30),
    retry_policy_max_attempts=2,
)
async def discover_context(question: str) -> str:
    """Search SLayer for relevant models/columns, then inspect them.

    Returns targeted schema context (only the relevant models) instead
    of dumping the entire warehouse schema into the LLM prompt.
    """
    search_svc = get_search()
    inspect_svc = get_inspect()

    # Step 1: semantic search — find relevant entities
    search_result = run_sync(
        search_svc.search(question=question, max_results=10)
    )

    # Collect unique model names from search hits
    model_names: set[str] = set()
    for hit in search_result.results:
        # hit.id is like "warehouse.fact_order.revenue"
        parts = hit.id.split(".")
        if len(parts) >= 2:
            model_names.add(parts[1])

    if not model_names:
        # Fallback: inspect the main fact table
        model_names = {"fact_order"}

    # Step 2: inspect each matched model for detailed schema
    context_parts: list[str] = []
    for model_name in sorted(model_names):
        try:
            detail = run_sync(inspect_svc.inspect(
                reference=model_name,
                entity_type="model",
                compact=False,
            ))
            context_parts.append(detail)
        except Exception:
            continue

    return "\n\n---\n\n".join(context_parts)


@workflows.activity(
    name="execute_warehouse_query",
    start_to_close_timeout=timedelta(seconds=30),
    retry_policy_max_attempts=2,
)
async def execute_warehouse_query(query_json: str) -> str:
    """Execute a SlayerQuery against the warehouse via SLayer engine."""
    engine = get_engine()
    try:
        query_dict = json.loads(query_json)
        query = SlayerQuery(**query_dict)
        result = engine.execute_sync(query=query)
        return json.dumps(result.data, default=str)
    except Exception as exc:
        return json.dumps({"error": str(exc)})


@workflows.activity(
    name="generate_query_plan",
    start_to_close_timeout=timedelta(seconds=90),
    retry_policy_max_attempts=2,
)
async def generate_query_plan(
    question: str,
    context: str,
    previous_error: str = "",
    client=Depends(get_mistral_client),
) -> str:
    """Ask Mistral to produce a SlayerQuery using discovered SLayer context.

    If previous_error is provided, it's fed back to the LLM so it can
    correct its output (e.g., remove invalid fields, fix column names).
    """
    system_prompt = QUERY_PLAN_SYSTEM.format(slayer_context=context)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": question},
    ]

    if previous_error:
        messages.extend([
            {"role": "assistant", "content": previous_error},
            {"role": "user", "content": (
                "The query above failed with an error. "
                "Fix the query — only use fields and columns from the schema. "
                "Respond with the corrected JSON."
            )},
        ])

    response = await client.chat.complete_async(
        model="mistral-large-latest",
        messages=messages,
        response_format={"type": "json_object"},
        max_tokens=1024,
    )
    return response.choices[0].message.content


@workflows.activity(
    name="analyze_results",
    start_to_close_timeout=timedelta(seconds=60),
    retry_policy_max_attempts=3,
    retry_policy_backoff_coefficient=2.0,
)
async def analyze_results(
    question: str,
    query_json: str,
    results_json: str,
    client=Depends(get_mistral_client),
) -> str:
    """Ask Mistral to produce a human-friendly analysis of query results."""
    user_content = (
        f"**Question:** {question}\n\n"
        f"**Semantic query:**\n```json\n{query_json}\n```\n\n"
        f"**Results:**\n```json\n{results_json}\n```"
    )
    response = await client.chat.complete_async(
        model="mistral-large-latest",
        messages=[
            {"role": "system", "content": ANALYSIS_SYSTEM},
            {"role": "user", "content": user_content},
        ],
        max_tokens=1024,
    )
    return response.choices[0].message.content

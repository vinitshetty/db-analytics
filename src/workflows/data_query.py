"""
Data Warehouse Query – conversational workflow for Vibe Work.

This module runs inside the Temporal deterministic sandbox, so it must NOT
import anything that does file I/O, network, or pathlib at module level.

All side-effectful work lives in activities.py (loaded outside the sandbox).
"""

import json

import mistralai.workflows as workflows
import mistralai.workflows.plugins.mistralai as workflows_mistralai

# Import activity *references* – the sandbox allows this because the actual
# function bodies only execute inside the activity worker, not the sandbox.
with workflows.workflow.unsafe.imports_passed_through():
    from src.workflows.activities import (
        analyze_results,
        discover_context,
        execute_warehouse_query,
        generate_query_plan,
    )


@workflows.workflow.define(
    name="data-warehouse-query",
    workflow_display_name="Data Warehouse Query",
    workflow_description=(
        "Ask business questions about orders, revenue, customers, and "
        "products in natural language.  Uses SLayer semantic layer over the "
        "local data warehouse."
    ),
)
class DataWarehouseQueryWorkflow(workflows.InteractiveWorkflow):
    """User asks a question in Vibe Work → SLayer discovers relevant schema
    → LLM builds a semantic query → SLayer executes it → LLM analyses
    the results → answer appears in Vibe Work."""

    @workflows.workflow.entrypoint
    async def run(self) -> workflows_mistralai.ChatAssistantWorkflowOutput:

        # ── greet & collect question ──────────────────────────────────
        workflows_mistralai.send_assistant_message(
            "I can answer questions about your data warehouse — orders, "
            "revenue, customers, products, and regions.\n\n"
            "What would you like to know?"
        )

        user_input = await self.wait_for_input(
            workflows_mistralai.ChatInput(
                prompt="Ask a business question",
                suggestions=[
                    "What is our total revenue?",
                    "Show revenue by region",
                    "Who are our top 5 customers?",
                    "Monthly revenue trend",
                    "Profit by product",
                ],
            )
        )
        question = " ".join(chunk.text for chunk in user_input.message)

        # ── progress steps shown in Vibe Work ─────────────────────────
        discover_item = workflows_mistralai.TodoListItem(
            title="Discovering relevant schema",
            description="Searching SLayer for models and columns",
        )
        plan_item = workflows_mistralai.TodoListItem(
            title="Building query plan",
            description="Using discovered context to generate a query",
        )
        query_item = workflows_mistralai.TodoListItem(
            title="Querying the warehouse",
            description="Running query via SLayer semantic engine",
        )
        analysis_item = workflows_mistralai.TodoListItem(
            title="Analyzing results",
            description="Generating insights from the data",
        )

        async with workflows_mistralai.TodoList(
            items=[discover_item, plan_item, query_item, analysis_item]
        ):

            # Step 1 – SLayer search + inspect → targeted context
            async with discover_item:
                context = await discover_context(question)

            # Step 2 – LLM generates a SlayerQuery using discovered context
            async with plan_item:
                raw_plan = await generate_query_plan(question, context)
                try:
                    plan = json.loads(raw_plan)
                    query_dict = plan.get("query")
                except json.JSONDecodeError:
                    return workflows_mistralai.ChatAssistantWorkflowOutput(
                        content=[workflows_mistralai.TextOutput(
                            text="Sorry, I couldn't understand your question. "
                                 "Could you try rephrasing it?"
                        )],
                        isError=True,
                    )

                # LLM indicated the data isn't available
                if query_dict is None:
                    reason = plan.get(
                        "reason",
                        "The requested data is not available in the warehouse.",
                    )
                    return workflows_mistralai.ChatAssistantWorkflowOutput(
                        content=[workflows_mistralai.TextOutput(text=reason)],
                    )

                query_json = json.dumps(query_dict)

            # Step 3 – SLayer executes the semantic query (with one retry)
            async with query_item:
                results_json = await execute_warehouse_query(query_json)
                results = json.loads(results_json)

                # If it failed, retry once — feed the error back to the LLM
                if isinstance(results, dict) and "error" in results:
                    error_context = (
                        f'{{"attempted_query": {query_json}, '
                        f'"error": "{results["error"]}"}}'
                    )
                    raw_plan = await generate_query_plan(
                        question, context, error_context,
                    )
                    try:
                        plan = json.loads(raw_plan)
                        query_dict = plan.get("query")
                        if query_dict is None:
                            reason = plan.get(
                                "reason",
                                "The requested data is not available "
                                "in the warehouse.",
                            )
                            return workflows_mistralai.ChatAssistantWorkflowOutput(
                                content=[workflows_mistralai.TextOutput(
                                    text=reason,
                                )],
                            )
                        query_json = json.dumps(query_dict)
                    except json.JSONDecodeError:
                        return workflows_mistralai.ChatAssistantWorkflowOutput(
                            content=[workflows_mistralai.TextOutput(
                                text=f"Query failed: {results['error']}"
                            )],
                            isError=True,
                        )

                    results_json = await execute_warehouse_query(query_json)
                    results = json.loads(results_json)

                    if isinstance(results, dict) and "error" in results:
                        return workflows_mistralai.ChatAssistantWorkflowOutput(
                            content=[workflows_mistralai.TextOutput(
                                text=f"Query failed after retry: "
                                     f"{results['error']}\n\n"
                                     f"Query attempted:\n```json\n"
                                     f"{query_json}\n```"
                            )],
                            isError=True,
                        )

            # Step 4 – LLM analyses the rows and writes a report
            async with analysis_item:
                analysis = await analyze_results(question, query_json, results_json)

        return workflows_mistralai.ChatAssistantWorkflowOutput(
            content=[workflows_mistralai.TextOutput(text=analysis)],
        )

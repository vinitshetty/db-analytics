"""
CLI helper to trigger a workflow execution.

Usage:
    python -m src.workflows.start data-warehouse-query '{"question":"What is total revenue?"}'
    make execute workflow=data-warehouse-query input='{"question":"total revenue?"}'
"""

import asyncio
import json
import sys

from mistralai import Mistral


async def main():
    if len(sys.argv) < 3:
        print("Usage: python -m src.workflows.start <workflow-name> '<json-input>'")
        sys.exit(1)

    workflow_name = sys.argv[1]
    raw_input = sys.argv[2]

    try:
        workflow_input = json.loads(raw_input)
    except json.JSONDecodeError as exc:
        print(f"Invalid JSON input: {exc}")
        sys.exit(1)

    client = Mistral()  # picks up MISTRAL_API_KEY from env

    print(f"Triggering workflow '{workflow_name}' ...")
    result = await client.workflows.execute_async(
        workflow_name=workflow_name,
        inputs=workflow_input,
    )
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())

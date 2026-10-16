"""
Worker discovery entrypoint.

Auto-discovers all workflow classes in src/workflows/ and starts
a Temporal-backed worker that connects to the Mistral orchestrator.

Usage:
    python -m src.discover          (from project root)
    make start-worker               (via Makefile)
"""

import importlib
import inspect
import pkgutil
from pathlib import Path

import mistralai.workflows as workflows


def discover_workflows() -> list:
    """Import every module under src/workflows/ and collect workflow classes."""
    pkg_path = Path(__file__).parent / "workflows"
    found = []

    for _importer, modname, _ispkg in pkgutil.iter_modules([str(pkg_path)]):
        mod = importlib.import_module(f"src.workflows.{modname}")
        for _name, obj in inspect.getmembers(mod, inspect.isclass):
            # Classes decorated with @workflow.define have __temporal_workflow_definition
            if hasattr(obj, "__temporal_workflow_definition"):
                found.append(obj)

    return found


async def main():
    wf_classes = discover_workflows()
    print(f"Discovered {len(wf_classes)} workflow(s):")
    for cls in wf_classes:
        print(f"  - {cls.__name__}")
    print()
    print("Starting worker – connected to Mistral orchestrator ...")
    print("Keep this terminal open.  Trigger from Vibe Work or CLI.\n")
    await workflows.run_worker(wf_classes)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())

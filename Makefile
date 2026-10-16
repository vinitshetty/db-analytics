.PHONY: start-worker execute setup generate-data test-slayer

# ── Worker ────────────────────────────────────────────────────────────────
# Start the local worker. It connects to the Mistral orchestrator and
# waits for workflow executions.  Keep this running in a terminal.
start-worker:
	uv run python -m src.discover

# ── Trigger a workflow execution from the CLI ─────────────────────────────
# Usage: make execute workflow=data-warehouse-query input='{"question":"total revenue?"}'
execute:
	uv run python -m src.start $(workflow) '$(input)'

# ── First-time setup ──────────────────────────────────────────────────────
setup:
	uv sync
	@echo ""
	@echo "Create a .env file with your Mistral API key:"
	@echo '  echo "MISTRAL_API_KEY=your-key-here" > .env'
	@echo ""
	@echo "Generate the data warehouse (if not already done):"
	@echo "  make generate-data"
	@echo ""
	@echo "Then start the worker:"
	@echo "  make start-worker"

# ── Data warehouse ────────────────────────────────────────────────────────
generate-data:
	python3 generate_data.py

# ── Quick test of the semantic layer (no Mistral key needed) ──────────────
test-slayer:
	python3 slayer_agent.py

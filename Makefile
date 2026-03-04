.PHONY: install test test-brain test-cockpit lint serve mcp clean help benchmark benchmark-report benchmark-ablation

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-18s\033[0m %s\n", $$1, $$2}'

install: ## Install all packages in dev mode
	pip install -e brain/[all]
	pip install -e cockpit/
	cd cockpit && npm ci

test: ## Run all tests
	pytest brain/tests/ cockpit/tests/ -v --tb=short

test-brain: ## Run brain tests only
	pytest brain/tests/ -v --tb=short

test-cockpit: ## Run cockpit tests (Python + JS)
	pytest cockpit/tests/ -v --tb=short
	cd cockpit && npx vitest run

lint: ## Lint all Python code
	ruff check brain/ cockpit/server/ cockpit/scripts/
	ruff format --check brain/ cockpit/server/ cockpit/scripts/

format: ## Format all Python code
	ruff format brain/ cockpit/server/ cockpit/scripts/
	ruff check --fix brain/ cockpit/server/ cockpit/scripts/

serve: ## Start cockpit dev server (http://localhost:8420)
	cd cockpit && python -m server.main

mcp: ## Start MCP server
	python -m engineering_brain.mcp_server

benchmark: ## Run full benchmark suite with PDF report
	cd brain && python -m benchmarks run

benchmark-report: ## Generate PDF from latest benchmark results
	cd brain && python -m benchmarks report

benchmark-ablation: ## Run ablation study with PDF report
	cd brain && python -m benchmarks ablation

clean: ## Remove build artifacts
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	rm -rf dist/ build/ .pytest_cache/ .ruff_cache/ .mypy_cache/ htmlcov/

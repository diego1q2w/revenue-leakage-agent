# Revenue Leakage Agent — dev commands
# Backend uses uv with the venv/ directory (kept for PyCharm compatibility).

UV := UV_PROJECT_ENVIRONMENT=venv uv
PY := venv/bin/python

.PHONY: install install-backend install-frontend backend frontend dev test test-backend reset-sandbox help

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

install: install-backend install-frontend ## Install all dependencies

install-backend: ## Sync Python dependencies into venv/
	$(UV) sync

install-frontend: ## Install Next.js dependencies
	cd frontend && npm install

backend: ## Run the FastAPI backend (http://localhost:8000)
	$(PY) -m uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000

frontend: ## Run the Next.js frontend (http://localhost:3000)
	cd frontend && npm run dev

dev: ## Run backend and frontend together
	$(MAKE) -j2 backend frontend

test: test-backend ## Run all tests

test-backend: ## Run backend tests
	$(PY) -m pytest backend/tests -v

reset-sandbox: ## Empty all sandbox ledgers, the audit log, and pending proposals
	@for f in invoices credit_memos plan_amendments audit_log proposals; do \
		echo "[]" > sandbox/$$f.json; \
	done
	@echo "sandbox reset."

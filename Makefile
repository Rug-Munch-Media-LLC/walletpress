SHELL := /bin/bash

.PHONY: help install dev lint format test typecheck security audit clean \
        docker-up docker-down changelog commit precommit ci

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install dependencies
	cd backend && pip install -r requirements.txt

dev: ## Start dev server
	cd backend && uvicorn main:app --reload --host 0.0.0.0 --port 8010

migrate: ## Run pending Alembic migrations
	cd backend && python3 -m alembic upgrade head

migration: ## Create new migration (usage: make migration msg="description")
	cd backend && python3 -m alembic revision --autogenerate -m "$(msg)"

lint: ## Lint and format code
	cd backend && ruff check . --fix && ruff format .

test: ## Run tests
	cd backend && python3 -m pytest tests/ -v --tb=short

test-cov: ## Run tests with coverage
	cd backend && python3 -m pytest tests/ --cov --cov-report=term-missing

typecheck: ## Run mypy type checking
	cd backend && mypy . --strict --ignore-missing-imports

security: ## Run security audit
	cd backend && bandit -r . --quiet --skip=B101,B311 && safety check

check: ## Full audit: lint + typecheck + security + test
	make lint && make typecheck && make security && make test

clean: ## Clean build artifacts
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache .mypy_cache .ruff_cache

devnet: ## Start local devnet (Solana + Anvil + x402)
	bash scripts/devnet.sh start

devnet-stop: ## Stop local devnet
	bash scripts/devnet.sh stop

devnet-status: ## Check devnet status
	bash scripts/devnet.sh status

docker-up: ## Start Docker services
	docker compose up -d

docker-down: ## Stop Docker services
	docker compose down

changelog: ## Preview changelog
	standard-version --dry-run 2>/dev/null || echo "Run: npx standard-version"

commit: ## Interactive commit with commitizen
	cz commit

precommit: ## Run all pre-commit hooks
	pre-commit run --all-files

license-audit: ## Check dependency licenses
	bash /home/dev/scripts/license-audit.sh

vuln-scan: ## Run vulnerability scan
	bash /home/dev/scripts/vuln-monitor.sh

pin-release: ## Pin release to IPFS + Arweave
	bash /home/dev/scripts/pin-release.sh $(tag)

web3-sign: ## Configure web3 commit signing
	bash scripts/git-web3-sign.sh setup

ci: lint test typecheck security ## Full CI pipeline

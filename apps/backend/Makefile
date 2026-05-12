.PHONY: help infra up down dev test lint format

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

infra: ## Start data layer (postgres, neo4j, redis, mosquitto)
	docker compose up -d postgres neo4j redis mosquitto

up: ## Start all services via docker compose
	docker compose up -d

down: ## Stop all services
	docker compose down

dev-core: ## Run core_orchestrator in dev mode
	uvicorn core_orchestrator.main:app --reload --port 8000

dev-persona: ## Run persona_engine in dev mode
	uvicorn persona_engine.main:app --reload --port 8001

dev-memory: ## Run memory_system in dev mode
	uvicorn memory_system.main:app --reload --port 8002

dev-voice: ## Run voice_layer in dev mode
	uvicorn voice_layer.main:app --reload --port 8003

dev-action: ## Run action_layer in dev mode
	uvicorn action_layer.main:app --reload --port 8004

dev-device: ## Run device_coordination in dev mode
	uvicorn device_coordination.main:app --reload --port 8005

dev-gateway: ## Run gateway_adapter in dev mode
	uvicorn gateway_adapter.main:app --reload --port 8006

dev-worker: ## Run Celery worker for memory pipeline
	celery -A memory_system.pipeline worker --loglevel=info --concurrency=2

test: ## Run all tests
	pytest -q

test-cov: ## Run tests with coverage
	pytest -q --cov=shared --cov=core_orchestrator --cov=persona_engine --cov=memory_system --cov=voice_layer --cov=action_layer --cov=device_coordination --cov=gateway_adapter

lint: ## Run ruff linter
	ruff check .

format: ## Run ruff formatter
	ruff format .

fmt-check: ## Check formatting without changes
	ruff format . --check

typecheck: ## Run mypy type checker
	mypy shared core_orchestrator persona_engine memory_system voice_layer action_layer device_coordination gateway_adapter

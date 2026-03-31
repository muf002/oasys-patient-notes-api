.PHONY: run down shell test lint format typecheck migrate migration

run:
	docker compose up --build

down:
	docker compose down

shell:
	docker compose exec app bash

test:
	uv run pytest tests/ -v

lint:
	uv run ruff check . && uv run ruff format --check .

format:
	uv run ruff format .

typecheck:
	uv run mypy app/

migrate:
	uv run alembic upgrade head

migration:
	uv run alembic revision --autogenerate -m "$(name)"

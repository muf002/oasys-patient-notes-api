.PHONY: run down shell test lint format typecheck migrate migration seed

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
	docker compose exec app uv run alembic upgrade head

migration:
	docker compose exec app uv run alembic revision --autogenerate -m "$(name)"

seed:
	docker compose exec app uv run python scripts/startup.py

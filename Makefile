.PHONY: setup dev check

setup:
	uv sync
	pnpm install --frozen-lockfile

dev:
	pnpm build:web
	uv run uvicorn roveredge.api:app --host 127.0.0.1 --port 8000

check:
	uv run pytest
	uv run mypy src
	uv run ruff check src tests
	pnpm test:web
	pnpm build:web

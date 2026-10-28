.PHONY: setup dev build-native compare-native-naive check train-risk-model

setup:
	uv sync
	$(MAKE) build-native
	pnpm install --frozen-lockfile

dev:
	pnpm build:web
	uv run uvicorn roveredge.api:app --host 127.0.0.1 --port 8000

build-native:
	uv run cmake -S native -B build/native -Dpybind11_DIR="$$(uv run python -m pybind11 --cmakedir)"
	uv run cmake --build build/native --config Release

compare-native-naive: build-native
	uv run python scripts/compare_native_naive.py

check: build-native
	uv run pytest
	uv run mypy src
	uv run ruff check src tests scripts
	pnpm test:web
	pnpm build:web

train-risk-model:
	uv run python scripts/train_risk_model.py

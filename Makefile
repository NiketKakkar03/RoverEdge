.PHONY: setup dev build-native compare-native-naive compare-native-blocked compare-native-parallel compare-native-accelerate check train-risk-model

setup:
	uv sync
	$(MAKE) build-native
	pnpm install --frozen-lockfile

dev:
	pnpm build:web
	uv run uvicorn roveredge.api:app --host 127.0.0.1 --port 8000

build-native:
	uv run cmake -S native -B build/native -DCMAKE_BUILD_TYPE=Release -Dpybind11_DIR="$$(uv run python -m pybind11 --cmakedir)"
	uv run cmake --build build/native --config Release

compare-native-naive: build-native
	uv run python scripts/compare_native_naive.py

compare-native-blocked: build-native
	uv run python scripts/compare_native_blocked.py

compare-native-parallel: build-native
	uv run python scripts/compare_native_parallel.py

compare-native-accelerate: build-native
	uv run python scripts/compare_native_accelerate.py

check: build-native
	uv run pytest
	uv run mypy src
	uv run ruff check src tests scripts
	pnpm test:web
	pnpm build:web

train-risk-model:
	uv run python scripts/train_risk_model.py

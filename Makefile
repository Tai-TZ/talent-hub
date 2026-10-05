.PHONY: api-types db-up db-down migrate seed run-be run-fe test-be test-fe lint typecheck check e2e audit

BE = backend
FE = frontend
PY = $(BE)/.venv/bin/python
ifeq ($(OS),Windows_NT)
PY = $(BE)/.venv/Scripts/python.exe
endif

# ---- Hạ tầng local ----
db-up:
	docker compose up -d postgres

db-down:
	docker compose down

# ---- Backend (BE) ----
migrate:
	cd $(BE) && ../$(PY) -m alembic upgrade head

seed:
	cd $(BE) && ../$(PY) -m src.cli seed-dev

run-be:
	cd $(BE) && ../$(PY) -m uvicorn src.main:app --reload --port 8000

test-be:
	cd $(BE) && ../$(PY) -m pytest --cov

# ---- Frontend (FE) ----
run-fe:
	cd $(FE) && npm run dev

test-fe:
	cd $(FE) && npm test

e2e:
	cd $(FE) && npm run e2e

# Sinh lại kiểu TypeScript của FE từ OpenAPI của BE (chạy sau mỗi lần đổi API)
api-types:
	cd $(BE) && ../$(PY) -m src.cli openapi --out ../$(FE)/openapi.json
	cd $(FE) && npm run api:types

# ---- Chất lượng ----
lint:
	cd $(BE) && ../$(PY) -m ruff check src tests migrations && ../$(PY) -m ruff format --check src tests migrations
	cd $(FE) && npm run lint

typecheck:
	cd $(BE) && ../$(PY) -m mypy src
	cd $(FE) && npm run typecheck

audit:
	cd $(BE) && ../$(PY) -m pip_audit -r requirements.txt
	cd $(FE) && npm audit --omit=dev --audit-level=high

check: lint typecheck test-be test-fe

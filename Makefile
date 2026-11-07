.PHONY: install api web test types seed

install:
	pip install -r requirements.txt --break-system-packages || pip install -r requirements.txt
	cd web && npm install

api:
	uvicorn backend.main:app --reload --port 8000

web:
	cd web && npm run dev

test:
	pytest -q

# generate all personas into the SQLite DB (idempotent; use with MOCK_DATA=0)
seed:
	python3 -m backend.data.seed

# regenerate frontend types from the running API (run `make api` first)
types:
	cd web && npx openapi-typescript http://localhost:8000/openapi.json -o src/types.gen.ts

.PHONY: install api web test types

install:
	pip install -r requirements.txt --break-system-packages || pip install -r requirements.txt
	cd web && npm install

api:
	uvicorn backend.main:app --reload --port 8000

web:
	cd web && npm run dev

test:
	pytest -q

# regenerate frontend types from the running API (run `make api` first)
types:
	cd web && npx openapi-typescript http://localhost:8000/openapi.json -o src/types.gen.ts

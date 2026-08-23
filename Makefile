.PHONY: infra backend worker scheduler frontend seed test demo-break demo-heal

infra:
	docker compose up -d postgres redis

install:
	cd backend && python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt -e ".[dev]"
	cd frontend && npm install

backend:
	cd backend && ./.venv/bin/uvicorn app.main:app --reload --port 8000

worker:
	cd backend && ./.venv/bin/arq app.workers.settings.WorkerSettings

scheduler:
	cd backend && ./.venv/bin/python -m app.scheduler.main

frontend:
	cd frontend && npm run dev

seed:
	cd backend && ./.venv/bin/python -m app.seed

test:
	cd backend && ./.venv/bin/python -m pytest tests -q

demo-break:
	cd backend && ./.venv/bin/python -m app.demo.break_scraper $(src)

demo-heal:
	cd backend && ./.venv/bin/python -m app.demo.trigger_healing $(src)

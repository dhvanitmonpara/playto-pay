# Playto Pay Payout Engine

Production-style hiring challenge implementation for a minimal merchant payout engine.

Playto Pay helps Indian merchants collect international payments in USD and later pays merchants in INR. This project focuses only on the INR merchant payout engine: ledger balances, idempotent payout requests, legal payout state transitions, and background worker processing.

## Tech Stack

- Backend: Django, Django REST Framework, PostgreSQL
- Worker: Celery, Redis
- Frontend: React, TypeScript, Tailwind CSS, Vite
- Local deployment: Docker Compose

## Project Layout

- `server/`: Django API, payout models, services, Celery tasks, tests
- `client/`: React dashboard
- `docker-compose.yml`: Postgres, Redis, backend, Celery worker, Celery beat, frontend
- `EXPLAINER.md`: design notes and correctness audit

## Local Setup

```bash
docker compose up --build
```

Services:

- Backend API: `http://localhost:8000/api/v1`
- Frontend: `http://localhost:5173`
- Postgres: `localhost:5432`
- Redis: `localhost:6379`

The backend container runs migrations and `seed_demo` on startup.

## Environment Variables

Backend:

```bash
DEBUG=1
SECRET_KEY=local-dev-secret
DATABASE_URL=postgresql://playto:playto@postgres:5432/playto_payments
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/0
CORS_ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
PAYOUTS_AUTO_ENQUEUE=1
```

Frontend:

```bash
VITE_API_BASE_URL=http://localhost:8000/api/v1
```

## Run Backend Without Docker

```bash
cd server
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo
python manage.py runserver
```

Without `DATABASE_URL`, the backend uses local SQLite for quick development. Use Postgres for the concurrency test and any real payout validation.

## Run Frontend Without Docker

```bash
cd client
npm install
npm run dev
```

## Run Celery

```bash
cd server
celery -A config worker -l info
celery -A config beat -l info
```

`process_pending_payouts` picks pending payouts. `retry_stale_processing_payouts` retries processing payouts older than 30 seconds and fails/refunds after 3 attempts.

## Seed Data

```bash
cd server
python manage.py seed_demo
```

Demo merchant IDs:

- `1`: Jaipur Textiles
- `2`: Kochi Spices
- `3`: Pune SaaS Labs

Each merchant has one bank account and multiple customer-payment ledger credits.

## API

Headers:

```http
X-Merchant-Id: 1
Idempotency-Key: 11111111-1111-4111-8111-111111111111
```

Endpoints:

- `GET /api/v1/merchants`
- `GET /api/v1/merchants/<id>/balance`
- `GET /api/v1/merchants/<id>/ledger`
- `GET /api/v1/payouts`
- `POST /api/v1/payouts`

Create payout:

```bash
curl -X POST http://localhost:8000/api/v1/payouts \
  -H 'Content-Type: application/json' \
  -H 'X-Merchant-Id: 1' \
  -H 'Idempotency-Key: 11111111-1111-4111-8111-111111111111' \
  -d '{"amount_paise":10000,"bank_account_id":1}'
```

## Run Tests

SQLite quick run:

```bash
server/.venv/bin/python server/manage.py test apps.payouts
```

Postgres run through Docker, including the concurrency test:

```bash
docker compose exec backend python manage.py test apps.payouts
```

The concurrency test is skipped on SQLite because SQLite does not support row-level `SELECT FOR UPDATE` locking.

## Deployment Notes

The app is deployable on any free/credit-tier platform that supports:

- a Dockerized web service for `server/`
- a Dockerized or static Vite frontend for `client/`
- managed PostgreSQL
- managed Redis
- a background worker process for Celery
- a scheduled worker process for Celery beat

For a simple deployment, run these process types:

- Web: `gunicorn config.wsgi:application`
- Worker: `celery -A config worker -l info`
- Scheduler: `celery -A config beat -l info`
- Frontend: `npm run build`, then serve `client/dist`

Set `DATABASE_URL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`, `SECRET_KEY`, `ALLOWED_HOSTS`, and `CORS_ALLOWED_ORIGINS` on the platform.

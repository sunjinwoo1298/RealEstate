# EstateFlow AI: running and deploying

Repository: https://github.com/sunjinwoo1298/RealEstate · Live app: https://real-estate-phi-lemon.vercel.app

## Architecture in one line

Next.js frontend (Vercel) → FastAPI backend (Render) → PostgreSQL with pgvector (hosted Postgres) + two worker processes (reminders, customer email).

>
## Run locally

Requirements: Python 3.9+, Node 20+, PostgreSQL with the `pgvector` extension (or a hosted one).

```bash
# 1. Backend
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r backend/requirements.txt
cp backend/.env.example backend/.env.local              # fill in the names listed below
alembic -c backend/alembic.ini upgrade head             # creates tables and the vector extension
python -m backend.cli.seed_demo                         # demo accounts + 3 sample enquiries
python -m uvicorn backend.main:app --reload --port 8000

# 2. Workers (two more terminals, same environment)
python -m backend.workers.reminder_worker
python -m backend.workers.customer_email_worker

# 3. Frontend
cd frontend
cp .env.example .env.local
npm install
npm run dev                                             # http://localhost:3000
```

Then, as admin, create a project in **Knowledge Base**, upload and approve a fact sheet, publish it, and set visit capacity and working hours under **Availability**.

## Deploy

**Backend + workers (Render):** New → Blueprint → select this repo (`render.yaml`). It creates the API (runs migrations before each deploy), the reminder worker, the email worker and Redis. Fill the secrets it asks for. Create the database separately (Prisma) and paste its URL into `DATABASE_URL` and `DIRECT_DATABASE_URL`. 

**Frontend (Vercel):** Import the repo, set **Root Directory = `frontend`**, framework Next.js, then set the two variables below and deploy. Finally put the Vercel URL into the backend's `CORS_ORIGINS`, `FRONTEND_BASE_URL` and `CUSTOMER_PORTAL_BASE_URL`, and redeploy the backend.

## Environment variables 

**Frontend **

| Name | Purpose |
|---|---|
| `NEXT_PUBLIC_API_URL` | `/api/v1`  |
| `BACKEND_URL` | `Render live URL`  |

**Backend: required**

`APP_ENV`, `DATABASE_URL`, `DIRECT_DATABASE_URL`, `JWT_SECRET_KEY`, `REFRESH_RECOVERY_KEY`, `GROQ_API_KEY`, `HF_TOKEN`, `CORS_ORIGINS`, `FRONTEND_BASE_URL`, `CUSTOMER_PORTAL_BASE_URL`, `COOKIE_SECURE`, `COOKIE_SAMESITE`, `EMAIL_PROVIDER`, `PYTHON_VERSION`

**Backend: optional**

`GROQ_MODEL`, `EMBEDDING_MODEL_NAME`, `EMBEDDING_DIMENSION`, `WEBHOOK_SOURCE_SECRETS`, `EMAIL_API_KEY`, `EMAIL_FROM_ADDRESS`, `EMAIL_FROM_NAME`, `EMAIL_REPLY_TO`, `EMAIL_SUPPORT_CONTACT`, `DEMO_PASSWORD`, `INITIAL_ADMIN_EMAIL`, `INITIAL_ADMIN_PASSWORD`, `COOKIE_DOMAIN`, `LOG_LEVEL`, and the `*_RATE_LIMIT_*`, `REMINDER_*`, `CUSTOMER_EMAIL_*` tuning values listed in `backend/.env.example` and `backend/core/config.py`.


## Demo login (reviewer)

Created by `python -m backend.cli.seed_demo`. Password for all demo accounts: `Demo@12345` (override with `DEMO_PASSWORD`; change it for any public deployment).

| Role | Sign in at | Email | Password |
|---|---|---|---|
| **Admin** | [/login](https://real-estate-phi-lemon.vercel.app/login) | `admin-smoke@estateflow.ai` | `Hello@1234` |
| **Sales head (manager)** | [/login](https://real-estate-phi-lemon.vercel.app/login) | `test2@estateflow.ai` | `09876543` |
| **Sales executive** | [/login](https://real-estate-phi-lemon.vercel.app/login) | `test@estateflow.ai` | `12345678` |


Suggested walk-through: as admin publish a project with a fact sheet and set availability; as the buyer open **Chat** (ask in Hindi or Gujarati, ask for a visit time, reply "yes" to book); as the sales head open **Conversations → Flagged for review** and **Analytics**; as the executive open **Handoff Queue** and **Site Visits**.

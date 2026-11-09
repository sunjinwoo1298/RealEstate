# EstateFlow AI

AI-assisted lead management and site-visit automation for residential property developers. Every enquiry is captured in one place, answered at once in **English, Hindi or Gujarati**, qualified from an approved fact sheet, and booked into a **real free slot**. Serious buyers are handed to a named salesperson with the full chat.

**Docs:** [Technical design](docs/EstateFlow_Technical_Design_Document.docx) · [Deployment & demo logins](deployment.md)

## Features

- **One lead list** from portals, social ads, hoarding calls, website and CSV, with source tags and duplicate detection (fuzzy matches are flagged, never auto-merged).
- **AI assistant** that answers only from approved fact sheets, never quotes a final price or discount, asks for missing needs (BHK, budget, purpose) and escalates what it cannot answer.
- **Booking in chat or on screen** against real availability: working hours, leave, capacity and existing visits. Concurrency-safe and idempotent, so no double booking.
- **Reminders** 1 day and 2 hours before a visit, with location map link and RERA number; consent and opt-outs are re-checked at send time.
- **Handoff** to a named executive with a summary, qualification and transcript.
- **Immediate first contact** for new enquiries (simulated channel), and a daily **flagged-chat review** for the sales head.
- **Dashboard**: first response time, answered within 2 minutes, not reached in 48 h, visits booked, show-up rate.
- **Admin tools**: fact-sheet versions and approval, project listing, executive availability, staff accounts, role-based access (buyer, executive, manager, admin).

## Screenshots

| Sales dashboard | Buyer on a phone |
|---|---|
| ![Sales dashboard](docs/screenshots/dashboard.jpg) | ![Buyer mobile menu](docs/screenshots/buyer-mobile-menu.jpg) |

| Answers only from the fact sheet | Price questions go to a salesperson |
|---|---|
| ![Fact-sheet answer](docs/screenshots/chat-fact-sheet-answer.jpg) | ![Price handoff](docs/screenshots/chat-price-handoff.jpg) |

## Architecture

```
Next.js (Vercel) ──/api/v1──▶ FastAPI (modular monolith) ──▶ PostgreSQL + pgvector
                                   │                      ──▶ Redis (rate limits, locks)
                                   ├─ Groq LLM + local multilingual embeddings
                                   └─ Workers: reminders · customer email
```

| Layer | Stack |
|---|---|
| Frontend | Next.js, TypeScript, Tailwind CSS |
| Backend | FastAPI, Pydantic, SQLAlchemy, Alembic |
| Data | PostgreSQL with pgvector, Redis |
| AI | Groq (LLM), sentence-transformers (retrieval) |
| Tests | Pytest |

The AI is a fixed pipeline (extract, retrieve, answer, guardrails) that calls validated backend services; it never runs SQL or confirms an action before the backend does.

## Quick start

```bash
# Backend
pip install -r backend/requirements.txt
cp backend/.env.example backend/.env.local        # fill in values
alembic -c backend/alembic.ini upgrade head
python -m backend.cli.seed_demo                   # demo accounts + sample enquiries
python -m uvicorn backend.main:app --reload --port 8000
python -m backend.workers.reminder_worker         # separate terminal
python -m backend.workers.customer_email_worker   # separate terminal

# Frontend
cd frontend && cp .env.example .env.local && npm install && npm run dev
```

Open <http://localhost:3000>. Full setup, environment variables and demo logins are in [deployment.md](deployment.md).

## Project layout

```
backend/    api/ (thin routes) · services/ · ai/ · models/ · workers/ · migrations/ · tests/
frontend/   app/ (staff, buyer and public pages) · components/ · lib/
docs/       technical design document
```

## Testing

```bash
pytest backend/tests          # run against a separate test database, never production
```

## Scope and next steps

Real WhatsApp/SMS, payments and voice calling are out of scope (messages are simulated and logged; email defaults to `log`). Next: cost per visit by source, a WhatsApp channel with opt-in templates, and a "reviewed" state for flagged chats.

## Compliance

Buyer contact data is personal data under the DPDP Act: contact only with consent, opt-outs (including replying STOP) are honoured, and promotional messages carry the project's RERA registration number.

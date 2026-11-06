# AGENT.md — EstateFlow AI

## 1. Project Overview
Build **EstateFlow AI**, an AI-powered real-estate lead management and site-visit automation platform for residential property developers.

The system must:
- Capture and centralize leads from multiple sources.
- Detect duplicate buyers while preserving source attribution.
- Provide multilingual AI conversations (English, Hindi, Gujarati).
- Qualify buyers and answer questions using approved project information.
- Schedule site visits using real executive availability.
- Transfer conversations to sales executives with complete context.
- Track reminders, attendance, conversions, and marketing performance.

**This is a business workflow automation platform, not just a chatbot.**

## 2. Technology Stack
- Frontend: Next.js, TypeScript, Tailwind CSS, shadcn/ui.
- Backend: Python, FastAPI, Pydantic.
- Database: PostgreSQL.
- ORM and migrations: SQLAlchemy, Alembic.
- Vector search: pgvector.
- Cache and background jobs: Redis, Celery or RQ.
- AI: Gemini or OpenAI API.
- Testing: Pytest, Playwright.
- Deployment: Vercel + Railway/Render.

Prefer a modular monolith. Do not introduce microservices, Kafka, Kubernetes, or multiple autonomous agents without a demonstrated requirement.

## 3. Architecture Principles
- Keep frontend, backend, AI orchestration, and domain services logically separated.
- PostgreSQL is the source of truth for all business data.
- AI orchestration must never directly execute arbitrary SQL or bypass domain services.
- AI tools must call validated backend service methods.
- Keep business logic independent of the LLM provider.
- Use structured SQL retrieval for exact facts and RAG for descriptive information.
- Persist conversation state; never rely exclusively on LLM chat history.
- Use background workers for reminders and asynchronous tasks.
- Record important business actions as events.
- Prefer simple, maintainable solutions over unnecessary abstractions.

## 4. Core Backend Modules
Organize backend code by business domain:
- `leads`: ingestion, normalization, deduplication, attribution, lifecycle.
- `conversations`: messages, persistent state, ownership.
- `ai`: orchestrator, prompts, extraction, retrieval, tools, guardrails.
- `booking`: availability, reservations, cancellations, rescheduling.
- `handoff`: escalation, assignment, summaries.
- `knowledge`: fact sheets, approval, versioning, retrieval.
- `notifications`: reminders, delivery status, retries.
- `analytics`: event tracking and business KPIs.
- `auth`: authentication, roles, permissions.
- `admin`: project configuration and executive schedules.

Keep API routes thin. Put business logic in services and data access in repositories where useful.

## 5. Lead Management Rules
- One canonical buyer profile can have multiple enquiry/source records.
- Normalize phone numbers and emails before matching.
- Prioritize exact phone/email matches and source external IDs.
- Use name similarity only as an additional signal.
- Never automatically merge ambiguous fuzzy matches.
- Preserve original source, campaign, timestamp, and enquiry payload.
- Maintain a clear lead lifecycle: NEW, AI_CONTACTED, QUALIFIED, VISIT_REQUESTED, VISIT_BOOKED, VISIT_COMPLETED, CONVERTED, LOST, OPTED_OUT.
- Keep lead status separate from conversation status.

## 6. AI Assistant Rules
Implement one controlled, state-aware AI orchestrator, not an unrestricted autonomous agent.

Responsibilities:
- Understand buyer intent and language.
- Extract structured requirements (project, BHK, budget, purpose).
- Ask only for missing or ambiguous information.
- Retrieve approved project information.
- Select from explicitly permitted tools.
- Escalate unsupported or sensitive questions.

Conversation states should include DISCOVERY, QUALIFIED, VISIT_REQUESTED, VISIT_BOOKED, and HUMAN_HANDOFF.

Persist structured qualification data and conversation state in the database.

### Knowledge and Guardrails
- Only use approved, valid, project-specific fact sheets.
- Version documents and retain source metadata for retrieved chunks.
- Use SQL for exact structured facts and pgvector for descriptive retrieval.
- Never invent amenities, specifications, prices, discounts, possession dates, or legal claims.
- Never quote final prices or discounts; hand off to a salesperson.
- If information is unavailable, explain that a salesperson will confirm.
- Support buyer-requested human handoff at any time.
- Preserve the buyer's preferred language.

## 7. AI Tool Boundaries
Expose only validated business tools, such as:
- `get_project_information`
- `get_available_slots`
- `book_site_visit`
- `reschedule_site_visit`
- `cancel_site_visit`
- `request_human_handoff`

The AI must never claim an action succeeded until the backend confirms it.
Validate all tool arguments and permissions server-side.

## 8. Booking and Scheduling Rules
- Availability must account for executive working hours, blocked periods, existing appointments, visit duration, and site capacity.
- Booking must be atomic and concurrency-safe.
- Use database transactions, appropriate locks, and PostgreSQL constraints.
- Prevent overlapping appointments, not merely duplicate start times.
- Support idempotency keys to prevent duplicate bookings.
- Confirm bookings only after successful transaction commit.
- Store timestamps consistently in UTC and display in Asia/Kolkata.
- Support cancellation, rescheduling, and attendance tracking.
- Record booking changes in an audit/event history.

## 9. Human Handoff and Notifications
- Conversation ownership must be explicit: AI_ACTIVE, PENDING_ASSIGNMENT, HUMAN_ACTIVE, RESOLVED.
- Do not let AI and salespeople send conflicting messages.
- Handoff must include buyer requirements, source, conversation summary, and visit details.
- Use background jobs for reminders (24 hours and 2 hours before visits).
- Recheck booking status and consent before sending notifications.
- Make notification jobs retryable and idempotent.
- Respect opt-outs and channel-specific messaging consent.

## 10. Security and Compliance
- Implement role-based access control for buyers, executives, managers, and admins.
- Verify ownership and permissions on every protected API.
- Protect buyer contact details and conversation history.
- Store consent status, source, channel, and timestamp.
- Enforce opt-outs in backend services.
- Keep API keys and secrets server-side.
- Audit sensitive operations and administrative changes.
- Follow applicable DPDP and RERA requirements.
- Promotional claims must use approved information and applicable project registration details.

## 11. Analytics and Observability
Record events such as LEAD_CREATED, AI_RESPONSE_SENT, LEAD_QUALIFIED, VISIT_BOOKED, VISIT_CANCELLED, VISIT_ATTENDED, HUMAN_HANDOFF, and LEAD_CONVERTED.

Track:
- First response time and SLA rate.
- Leads not reached within 48 hours.
- Lead-to-visit conversion.
- Visit show-up rate.
- Cost per visit.
- Source-wise conversion.
- AI latency, retrieval results, tool calls, failures, and escalations.

Do not count future appointments as no-shows. Clearly define reporting periods and metric denominators.

## 12. Coding and Testing Standards
- Use TypeScript strictly; avoid `any`.
- Use Pydantic schemas for API validation.
- Use SQLAlchemy models and Alembic migrations.
- Keep functions focused and business logic testable.
- Handle errors explicitly; never silently swallow exceptions.
- Never commit secrets, credentials, or real buyer personal data.
- Add tests for every important business rule.
- Test duplicate ingestion, permissions, AI guardrails, handoff, booking concurrency, idempotency, and reminder cancellation.
- Use deterministic assertions for business-critical behaviour.
- Run relevant tests before considering a feature complete.

## 13. Implementation Priority
Build incrementally:
1. Project setup, database, authentication, and RBAC.
2. Lead ingestion, deduplication, and lead dashboard.
3. Conversation persistence and buyer chat.
4. AI qualification, approved knowledge retrieval, and guardrails.
5. Availability and concurrency-safe booking.
6. Human handoff and sales workspace.
7. Background reminders and attendance.
8. Analytics, AI evaluations, observability, and deployment.

## 14. Instructions for Coding Agent
- Read the existing codebase before making changes.
- Follow existing project conventions and avoid unnecessary rewrites.
- Do not assume a feature exists; inspect the implementation first.
- Before implementing major features, explain the proposed approach and affected files.
- Implement in small, verifiable steps.
- Do not create placeholder business logic for critical workflows.
- Do not hardcode project facts, executive schedules, or credentials.
- Update tests and documentation when changing behaviour.
- Report files changed, implementation decisions, and test results after each task.
- Ask for clarification when a business rule is ambiguous rather than inventing one.

**Primary objective: Build a reliable, secure, measurable real-estate sales automation product in which AI assists the workflow but the backend remains in control.**
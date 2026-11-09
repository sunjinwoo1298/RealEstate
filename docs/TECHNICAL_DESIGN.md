---
title: "EstateFlow AI: Technical Design Document"
---

**GitHub:** `<ADD YOUR REPOSITORY URL HERE>`  
**Live app:** `<ADD YOUR VERCEL URL HERE, if deployed>` (API on Render: `<ADD URL>`)

# 1. What it is

A lead-to-site-visit platform for a residential developer (Company A, Ahmedabad). Every enquiry, whether from a portal, social ad, hoarding number or the website, lands in one list, gets an immediate reply in English, Hindi or Gujarati, is qualified by an AI assistant that answers only from the approved fact sheet, and is booked into a real free slot. Serious buyers go to a named salesperson with the chat. Roles: buyer, sales executive, manager (sales head), admin.

# 2. Architecture and why

| Layer | Choice | Why |
|---|---|---|
| Frontend | Next.js + TypeScript + Tailwind, on Vercel | One app for buyers (phones) and staff; fast to ship; `/api/v1` is proxied to the backend so cookies stay first-party |
| Backend | FastAPI (Python), modular monolith | Async, typed (Pydantic) APIs; one deployable unit instead of microservices for a 6-week build |
| Database | PostgreSQL + pgvector | One source of truth for business data; vector search for fact-sheet retrieval; constraints and row locks make booking safe |
| Background | Two small worker processes + Redis | Reminders (1 day / 2 hours) and customer emails must run without a request; Redis also rate-limits and locks AI turns (fails open) |
| AI | One controlled orchestrator calling Groq; local multilingual embeddings | Not an open-ended agent: a fixed pipeline with explicit tools, so the backend stays in control |

Code is split by business domain (`leads`, `conversations`, `ai`, `booking`, `handoff`, `knowledge`, `notifications`, `analytics`, `auth`). API routes are thin; services hold the rules. The LLM never touches SQL: it can only call validated service methods.

# 3. Data model

- **Lead** (one canonical buyer) has many **LeadSource** rows (portal, social, hoarding, website, manual, CSV) so source, campaign and original payload are never lost. Phones and emails are normalised first; exact matches merge, and a fuzzy name match is only *flagged* (**PotentialDuplicateMatch**) for a human.
- **Conversation** and **Message** persist the chat, its state (DISCOVERY, QUALIFIED, VISIT_REQUESTED, VISIT_BOOKED) and ownership (AI_ACTIVE, PENDING_ASSIGNMENT, HUMAN_ACTIVE, RESOLVED). Each AI message stores its guardrail flags and tool calls.
- **LeadQualification** (project, BHK, budget, purpose, language).
- **Project**, **KnowledgeDocument**, **KnowledgeChunk** (versioned, approved fact sheets with embeddings).
- **AvailabilityRule**, **BlockedPeriod**, **ProjectVisitCapacity**, **SiteVisit**, **VisitEvent** (audit trail), **VisitReminder**.
- **Handoff**, **ConversationAssignment** (named executive, summary).
- **User** (staff), **CustomerAccount** and sessions, **CustomerNotificationDelivery** (email outbox).
- Lead status (NEW, AI_CONTACTED, QUALIFIED, VISIT_BOOKED, VISIT_COMPLETED, CONVERTED, LOST, OPTED_OUT) is kept separate from conversation status.

# 4. Main flows

1. **Enquiry in.** A signed webhook, CSV or manual entry is normalised, matched or created, and the source is recorded. For portal, social, hoarding and website enquiries the first reply is sent at once (simulated channel), so first-response time is measured.
2. **Chat.** The buyer's message goes to the orchestrator (below). A buyer can ask for a person at any time.
3. **Booking.** Availability = working hours minus blocked periods, existing visits and capacity, per executive. Booking runs in one transaction with locks and an idempotency key, so two buyers can never take the same slot (tested with concurrent requests). A confirmation is shown only after commit.
4. **Reminders.** Visit creation schedules the 24 h and 2 h reminders. The worker rechecks the booking version, status and consent before sending, retries with backoff, and skips opted-out buyers.
5. **Handoff.** Price asks, complaints, unsupported questions or a request for a person create a Handoff with a summary and a named executive. After that the AI stays silent so it never talks over the salesperson.
6. **Review.** The sales head opens "Flagged for review" each day. The dashboard shows response time, visits and show-up rate.

# 5. How the AI part works

One turn is a fixed pipeline: (1) **Extract**: an LLM call returns JSON (language, intent, project, BHK, budget, purpose, visit date and time, wants-a-person). (2) **Retrieve**: exact facts come from SQL (project record); descriptive facts come from pgvector search over *approved* fact-sheet chunks only. (3) **Answer**: a second LLM call writes the reply from that context only. (4) **Guardrails in code**, not just in the prompt: any reply containing a price or discount figure is replaced by a safe message and the chat is escalated; missing facts become "a person will confirm"; prompt-injection attempts are flagged; STOP opts the buyer out without calling the LLM.

**Booking tool.** For visit requests the reply is built by the backend, not the LLM: it reads the real calendar, lists free times in IST, asks the buyer to confirm one, and books through the booking service only on "yes". It says "booked" only after the transaction commits. Language follows the buyer (EN, HI, GU). State and qualification are saved in the database, not only in the LLM history.

# 6. UI and design decisions

Calm, minimal and premium to match the price of the homes: warm off-white background, one deep green and one terracotta accent, generous white space, clear type, and nothing on screen without a purpose (developer health badges and dead buttons were removed).

- **Buyer on a phone:** short flow of project, chat, then a three-step booking (project, time, confirm). A menu button replaces the wide header below 768 px; chat links are tappable; the confirmation shows location, a map link and the RERA number.
- **Sales executive:** a handoff workspace with the summary, source, qualification, visits and full transcript beside the reply box, so nobody has to ask the buyer to repeat themselves.
- **Sales head:** a dashboard of first response, answered within 2 minutes, not reached in 48 hours, visits and show-up, plus one-click flagged-chat review.
- **Duplicate review** shows both records side by side and never merges automatically.

# 7. What was cut, and what next

**Cut (on purpose):** real WhatsApp/SMS (messages are simulated and logged; email provider is `log` by default), payments and allotment letters, outbound voice calls, a separate CRM, microservices.

**Next:**

1. Cost per visit by source (needs a spend table and an editor).
2. A real WhatsApp channel with opt-in templates.
3. Mark flagged chats "reviewed", and daily digests.
4. Pick executives by load and language.
5. Staff UX polish (pickers instead of raw IDs, confirmations).
6. A fixed-size embedding service so the API container can be smaller.

# 🖥️ Platform Architecture (Frontend + Backend)
**Status:** Designed (July 2026), implementation pending — backend architecture 11.07.2026, interface concepts 11–12.07.2026
**Role:** The product layer that turns the agents into a service: user cabinets for both sides of the procurement market, an API gateway, task queue, billing, and notifications

---

## Two Users, Two Entry Points

The platform serves both sides of the procurement market, each with its own cabinet and its own natural starting point:

| User | Cabinet | Everything starts with… |
|------|---------|--------------------------|
| **Participant** (SME director / tender manager / lawyer running several clients) | Participant cabinet | **a Prozorro tender number** — every feature (report, checklist, package, winner analysis, complaint) branches from a specific tender |
| **Buyer** (a contracting authority's authorized person, often without a lawyer) | TD constructor cabinet | **the kind of procurement** — a category pick or a free-text subject / CPV code, classified automatically |

---

## Participant Flow: a Phase Path, Not Tabs

The tender detail screen follows the tender's actual lifecycle — the interface leads by the hand; future steps are visible but locked until their phase opens:

```
STEP 1. DECISION   ("enter or not?")  → TD analysis · contract review · buyer profile ·
                                        spec-tailoring check · [appeal TD conditions before deadline]
STEP 2. PREPARATION                   → checklist · package generation · pre-submission
                                        check of YOUR OWN package · submission guide
STEP 3. REVIEW                        → [if the 24-hour correction window opens: alert + regeneration]
STEP 4. RESULT                        → win: winner package with 4-day deadlines
                                        loss: analysis of the WINNER's bid → grounds to appeal (4-day window)
STEP 5. CONTRACT                      → signing package · final reminders
```

Cross-cutting: a full chronology of milestones and deadlines, and a complaint wizard fed by grounds found in the analyses. Deadlines are computed from Prozorro dates and legal norms, never hardcoded.

## Buyer Flow: a Wizard, Not a Form

TD creation is a step-by-step wizard (one decision per step, back-navigation allowed): procurement kind → details → base requirements package (pre-checked) → specific requirements with live precedent-backed risk warnings → risk review summary → generation → optional self-check "through a participant's and complainant's eyes." The buyer cabinet also tracks the buyer's own statutory obligations (proposal review deadlines, the 24-hour correction duty, publication timers) with reminders.

---

## Frontend

- **Design system — "dark chrome + light canvas."** Navigation, sidebar, and footer carry the brand's dark language (continuous with the public site); the working canvas — reports, checklists, constructors — is light ("paper"): users read dense legal text for hours, and the canvas matches the white DOCX outputs they download.
- **Unified status language** across all products (ready / in progress / designed / violation / "user decides" attention badges), with the accessibility rule that status is never conveyed by color alone.
- **Staged delivery:** Streamlit MVPs first; everything user-facing talks to the backend **through the API from day one**, so the later full frontend replaces only the UI layer — the same API contract, zero backend changes.
- **Telegram notifications** as a first-class channel alongside in-cabinet badges and e-mail. Every long analysis ends with a "✅ Ready — Open" push, so progress screens can honestly say "you may close this page — we'll message you when it's done." Urgent deadline classes (24-hour correction window, appeal deadline tomorrow) always go to Telegram. Each notification is one action: urgency + what to do + by when + a single deep-link button.

---

## Backend

The backend's mission: make the agents a product without duplicating them. Agents are already built as pure Python core libraries — the backend is a **thin wrapper over those cores plus infrastructure subsystems**. It contains no agent business logic, renders no UI, and stores no knowledge.

| Subsystem | Purpose |
|-----------|---------|
| **API Gateway (FastAPI)** | Route domains mirror the cabinet screens; a versioned OpenAPI schema is the binding contract for every frontend generation |
| **Task queue** | The heart of the backend — analyses run for minutes to hours. Full task lifecycle with statuses and progress; progress stages are read from the agents' own checkpoint logs; transient-error retries; idempotent re-runs resume from checkpoints (the agents already support resume). A cost estimate precedes every paid run |
| **Auth + tenancy** | Roles (participant / buyer / staff); client isolation enforced in every data-access layer, files included; Telegram account linking via one-time code |
| **Billing** | Subscription plans with quotas for regular actions + metered add-ons for episodic LLM-heavy features; a single charge resolver so the UI always shows the state (included / add-on / upgrade) *before* the click; a **cost ledger** records both customer price and LLM cost per task for unit economics; card checkout only via a payment provider's hosted page |
| **Notification service** | Channels: cabinet badge, e-mail, Telegram bot; notification classes with quiet-hours rules; "result ready" always delivered |
| **Scheduler** | Cron jobs compute tender phase milestones from Prozorro dates (appeal deadlines, 24-hour windows, winner deadlines, buyer obligations) and feed both notifications and the UI phase ribbons — one data model for both |
| **Agent adapters** | One per agent, a uniform contract: estimate → run → progress → result. Direct core-library calls, no subprocesses |

Product data lives in a dedicated application database, deliberately separate from the agents' knowledge stores; existing databases keep their established access rules.

---

## ☁️ Cloud Credits Usage Plan

The platform's knowledge bases are its moat, and populating them is fundamentally an **LLM-volume problem**. The agents already run on Gemini (2.5 Flash for analysis and extraction, 3.5 Flash where it complements it — including a two-model ensemble for technical-spec comparison where each model catches manipulations the other misses). Cloud credits convert directly into knowledge:

| Workload | What the credits buy |
|----------|----------------------|
| **Mass processing of PPOU decisions** | Thousands of appeals-body decisions (4,400+ collected, growing) analyzed by `oopz_researcher` via Gemini API → the precedent database that powers risk cards, buyer profiles, complaint drafting, and TD risk warnings |
| **Requirements knowledge base** | ~100 real TDs × 13 procurement categories processed in a lightweight extraction mode → the base packages, parameter medians, and safe ranges behind the TD constructor |
| **AMCU decisions backfill** | Full-text Gemini analysis of bid-rigging decisions → the evidence/reasoning base for the `investigation` agent |
| **Live user analyses** | Production tender/bid analyses for real users — the per-analysis LLM spend of the working product |
| **Hosting and scaling** | The move from a single Docker host to managed cloud: Cloud Run for agent autoscaling, Cloud SQL for the PostgreSQL databases, Vertex AI as the unified model access path, Cloud Storage for documents and reports, BigQuery for analytics across procurement participants |

The knowledge bases are self-reinforcing: every additionally processed decision improves every subsequent analysis, and each regular analysis run feeds requirements and templates back into the bases as a free by-product.

---

## Delivery Order

1. Streamlit MVPs of the constructors (td_creator, bid_creator) over their pure cores
2. Backend subsystems: gateway, task queue, auth, notifications — API-first
3. Billing and scheduler
4. Full frontend over the same OpenAPI contract

---

## Current State (July 2026)

Backend architecture and the full interface concept package (design system, participant cabinet, buyer constructor, ops console, news/statistics) are designed and internally cross-referenced; key screens are accompanied by static HTML mockups. Implementation has not started. Open items deliberately deferred to implementation spikes: queue technology (Postgres-backed v1 vs. Redis), payment and e-mail provider selection, full-frontend stack (isolated from the backend by the OpenAPI contract by design).

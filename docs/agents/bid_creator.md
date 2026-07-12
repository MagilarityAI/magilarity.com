# 📦 Bid Creator
**Status:** Designed (July 2026), implementation pending — architecture approved 10.07.2026
**Role:** Generates a participant's bid document package against the tender requirements checklist — the producer counterpart to `bid_researcher`'s independent verification

---

## Purpose

Preparing a bid package is hours of repetitive drafting: qualification certificates, guarantee letters, consents, experience references — each one bound to a specific clause of the tender documentation. `bid_creator` takes the machine-readable requirements checklist produced by `tender_doc_researcher`, combines it with the participant's organization profile, and generates the simple documents completely, scaffolds the semi-automatic ones, and gives an honest action plan for everything that must remain the participant's own work.

**Proposal of documents, not a submission.** The user can edit everything and submits the package themselves. Complex documents (technical specifications, cost estimates) are explicitly the user's responsibility — with maximum assistance around them.

**Full market symmetry, producer and verifier deliberately separated:**

```
BUYER:        td_creator  (creates TD)      ←verified by— tender_doc_researcher
PARTICIPANT:  bid_creator (creates package) ←verified by— bid_researcher   ← THIS AGENT
```

The generated package can be self-checked through `bid_researcher` — an independent review by the very same tool that analyzes real submitted packages.

---

## The Organization Profile — the Heart of the Generator

A mandatory, one-time profile per participant (multi-tenant by `client_id` from day one — the target users are external participants):

| Section | Contents |
|---------|----------|
| Identity | name, EDRPOU, address, director (name/position/authority), bank, contacts |
| Experience | analogous contracts (subject, buyer, amount, dates, completion status) |
| Personnel & equipment | staff qualifications, machinery/equipment with ownership status |
| **Document vault** | licenses, ISO certificates, charter, extracts — file + metadata + **validity period**, with expiry checked against each tender's submission deadline |
| **Style (mandatory)** | writing style (from expansive to terse) + typography (font, size, spacing, emphasis, heading style) |

A generated certificate = template × profile × tender details × style.

---

## Three-Layer Checklist Classification

Each checklist item is deterministically routed into one of three groups:

| Group | Meaning | Examples |
|-------|---------|----------|
| ✅ **Generate fully** | template exists and all slots are covered by profile + tender data | Art. 16/17 qualification certificates, experience/personnel/equipment references, guarantee letters, consents, draft-contract acceptance letter |
| ⚠️ **Scaffold** | template exists but needs user data | price proposal (the price), references with delivery specifics — document generated with highlighted fill-in fields |
| ❌ **Yours + assistance** | agent won't generate it, but helps | technical spec (requirements extracted from TD as a reminder); bank guarantee → a ready **bank application** with the TD's parameters (amount, term, beneficiary, conditions); official extracts/licenses → packaged from the vault if valid, or a "where to obtain it" checklist |

---

## Verbatim Binding to the TD (the key anti-rejection defense)

Every generated document opens with an explicit reference to the requirement it satisfies — "in fulfillment of clause X, section Y of the tender documentation…" — quoting the checklist's `td_quote` verbatim. Formal rejections most often exploit loose wording; literal binding to the requirement minimizes that attack surface.

---

## Anti-Uniformity by Design

An unusual constraint: **our own `investigation` agent catches colluders precisely by shared document templates.** A generator that made all clients' documents identical would manufacture false collusion signals. Mitigations are built into the design:

- Writing style + typography are **mandatory** profile fields — different clients get different wording *and* different-looking documents
- A mandatory disclaimer "created by the bid_creator agent" in generated documents (transparency decision)
- Clean file metadata
- A configurable conflict guard: if a package was already generated for the same tender for another client, a uniformity-risk warning fires (activation policy is a deployment decision)

---

## Phase Packages — the Package Lives with the Tender

The same phase chronology used across the platform:

| Phase | What's generated |
|-------|-------------------|
| Proposal | full initial package |
| **24-hour correction** | input: the buyer's non-compliance notice or a `bid_researcher` report → regeneration of exactly the flagged documents + a cover letter on remediation. A closed producer↔verifier loop |
| Winner | action plan with deadlines from the winner checklist (4-day items flagged: what to order immediately because it won't arrive in time) + generated documents of this stage |
| Signing | signing-stage documents per checklist |

---

## Template Base (Phase A, continuous)

Templates are mined **retrospectively at no LLM cost** from the document index of packages already analyzed by `bid_researcher` (documents are already classified and described there), plus a hook on new runs. Gemini 2.5 clusters wordings of each document type into a canonical template with profile/tender slots and per-style variants. **Other participants' unique content is never copied** — only structure and boilerplate phrasing are canonicalized.

---

## Model Routing

| Role | Model |
|------|-------|
| Template canonicalization (Phase A) | Gemini 2.5 Flash |
| Style adaptation of text to the profile | Gemini 2.5 / Claude Sonnet (spot use) |
| Document assembly, checklist classification, package assembly, typography | No LLM — deterministic |
| Self-check | `bid_researcher`'s own pipeline |

---

## Output per Package

- Generated DOCX documents with correct file-naming conventions
- Package cover sheet: what to upload to Prozorro and in what order; what the generation covered; what remains with the user (tech spec, bank guarantee, extracts)
- Bank guarantee application (when the TD requires one)
- Expiry warnings for vault documents that lapse before the deadline
- Optional self-check via `bid_researcher`: "N of M checklist items covered; discrepancies: […]"

---

## Architecture Principle: Pure Core, Thin UI

Same pattern as `td_creator`: all logic in a pure Python library, Streamlit MVP as a thin layer, future frontend wrapping the identical core. Natural eval: self-check coverage plus comparing a generated package against the participant's real package on a historical tender.

---

## Current State (July 2026)

Architecture and both algorithms (template base + participant flow) fully designed 10.07.2026. No implementation code written yet. Out of MVP scope: generating tech specs / cost estimates / bank guarantees themselves, automatic upload to Prozorro, full external-user authentication (schema carries `client_id` from day one; MVP uses simple profile selection).

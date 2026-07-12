# 🏗️ TD Creator
**Status:** Designed (July 2026), implementation pending — architecture approved 10.07.2026
**Role:** Tender documentation constructor for contracting authorities (buyers) — assembles a complete draft TD from a requirements knowledge base with live, precedent-backed risk warnings

---

## Purpose

A buyer's procurement officer — often running tenders part-time, without a lawyer — faces two recurring pains: complaints that derail procedure deadlines, and uncertainty about whether a given requirement is lawful. `td_creator` addresses both: the buyer picks a procurement category, reviews a pre-assembled set of requirements (checkboxes + parameters) with warnings drawn from real appeals practice, and receives a **proposed** complete TD as an editable Word file.

**Proposal, not decision:** the final document and the responsibility for it stay with the buyer's authorized person — the same "a human decides" principle as `complaint_researcher`.

**Unique position — we hold both sides of the market:** the constructor knows exactly how its TD will be seen by our own participant-side analyzer (`tender_doc_researcher`) and by a potential complainant, *before* publication.

```
td_creator (TD creation, buyer side)  ← THIS AGENT
    ↓ publication in Prozorro
tender_doc_researcher (TD analysis, participant side) → bid_researcher
    ↓ complaints
complaint_researcher / oopz_researcher        investigation (collusion)
```

---

## The Requirements Knowledge Base — the Core Asset

Requirements are harvested from **mass processing of real TDs** (via `tender_doc_researcher`), clustered across the 13 canonical procurement categories:

| Layer | Definition | UI behavior |
|-------|------------|-------------|
| Base | appears in >50% of the category's TDs | pre-checked |
| Common | 10–50% | unchecked, added deliberately |
| Specific | <10% | unchecked, added deliberately |

Practitioner insight behind the design: roughly half the requirements within a category are the same across buyers.

**A requirement = text + parameters.** What gets appealed is usually not the requirement but its parameter (3 ISO certificates instead of 1; a 5% bid security instead of 3%). The base stores median values and a safe range (p25–p75) per parameter; the constructor suggests the norm and highlights departures from it immediately.

Two ingestion paths keep the base growing: a lightweight extraction-only mode (requirements only, no full 16-point analysis — far cheaper than a full `tender_doc_researcher` run) for mass backfill, plus a hook that makes every regular `tender_doc_researcher` run contribute its extracted requirements as a free by-product.

---

## Risk Profiles from Real PPOU Practice (the killer feature)

Every canonical requirement is linked to the `oopz_decisions` precedent database: how many times similar requirements were appealed, with what outcomes, and in which decisions. Warnings fire **live, at the moment a checkbox is ticked or a parameter is set**:

- 🔴 "A similar requirement was appealed N times, M satisfied (decisions No. …). Safer wording from practice: '…'"
- 🟡 "Parameter above the category's safe range (median X)"
- 🟡 Deterministic anti-discrimination patterns from practice (certificates demanded in the *participant's* name instead of the manufacturer's; local-office requirements; requirement combinations typical of supplier tailoring)

Warnings cite decision numbers, never abstract morality. "No precedents found" is reported honestly as a lack of data, not as zero risk. The buyer may keep a risky requirement — their right and responsibility — and every shown warning is recorded in an accompanying memo for the authorized person.

---

## Normative Skeleton

The TD skeleton is the officially approved **model TD form** plus the mandatory elements of Art. 22 of Law No. 922 — these render always, with no checkboxes (checkboxes exist only where the buyer has discretion). The current wording of the model form and the law is fetched from the legislation database at implementation time, never hardcoded. A reference block lists the category's profile regulations (food safety, electricity market, security services, etc.), including the link "this regulation justifies these typical requirements."

---

## Two Modes

| Mode | Flow |
|------|------|
| **(a) From scratch** | category → skeleton + Art. 22 mandatory elements → base package pre-checked → specific requirements + parameters with medians/safe ranges → generate |
| **(b) From the buyer's draft** | upload own TD → parse (reusing `tender_doc_researcher`'s file extraction) → map onto the requirements base → "X requirements recognized; gaps vs. the category's base package: […]; risky spots: […]" → complete via checkboxes |

---

## Deterministic Assembly, Minimal LLM

The TD text is **assembled deterministically** from the skeleton plus canonical wordings from the base with the chosen parameters — the LLM does not "write the TD," so normative wording carries zero hallucination risk.

| Role | Model |
|------|-------|
| Requirement extraction from TDs (base population), wording clustering | Gemini 2.5 Flash |
| Occasional smoothing of specific free-text sections | Claude Sonnet (spot use) |
| TD assembly, parameters, checklist export, risk warnings | No LLM — deterministic |
| Self-check | `tender_doc_researcher`'s own pipeline |

---

## Output per Generation

- `PROPOSED_TD.docx` + annexes (bid form, technical requirements) — ready for editing in Word
- Accompanying memo (choices made, warnings shown, profile regulations) for the authorized person
- **Machine-readable requirements checklist** in the same handoff format `tender_doc_researcher` passes to `bid_researcher` — tenders born from our constructor never need reverse-engineering by our own analyzers
- Optional **self-check**: the generated TD is run through `tender_doc_researcher`'s full 16-point analysis — "how a participant and a complainant will see it." Target: zero violations, zero appeal grounds *before* publication. This doubles as the agent's natural eval.
- Optional analysis of the buyer's own draft contract (reusing the contract analyzer) — the agent deliberately does **not** generate contracts
- When editing an already-published TD: a "was/became" amendments file with deadline reminders (per CMU Resolution No. 1178 rules)

---

## Architecture Principle: Pure Core, Thin UI

All functionality (requirements base, risk analysis, DOCX generation) lives in a pure Python library with clear contracts and zero UI dependencies. The Streamlit MVP is a thin layer calling that core; the future full frontend (via FastAPI) wraps the same core with no rewriting.

---

## Current State (July 2026)

Architecture and both algorithms (base population + buyer wizard) fully designed 10.07.2026. No implementation code written yet. Base population plan: 2–3 priority categories incrementally before cloud-credit funding; a mass run of ~100 TDs × 13 categories in extraction mode once credits are available. Out of MVP scope: contract generation, competition profiling, multi-lot construction wizard, Q&A assistant.

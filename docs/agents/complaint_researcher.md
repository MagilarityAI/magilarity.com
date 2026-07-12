# 📨 Complaint Researcher
**Status:** Designed (July 2026), implementation pending — architecture approved 07.07.2026
**Role:** Reviews procurement complaints filed with the Appeals Body (PPOU) and drafts a **decision proposal** for a human specialist

---

## Purpose

When a tender participant files a complaint with Ukraine's Procurement Appeals Body (PPOU / ООПЗ), a specialist must weigh the complainant's arguments against the buyer's explanations, establish facts, apply the law, and issue a reasoned decision. `complaint_researcher` performs this research and prepares a **draft decision** — the human specialist reviews, edits, and decides.

**Draft, not decision — by principle.** The agent structures, argues, and proposes; a person judges. The same principle already governs the platform's technical-spec analysis ("the agent doesn't judge, the user decides").

**Why the agent is conceptually "almost ready":** its three suppliers already exist. `tender_doc_researcher` provides TD-analysis patterns, `bid_researcher` provides bid-vs-requirements verification patterns, and `oopz_researcher` provides the precedent database. What's new is the adversarial argument analysis and the decision drafter.

---

## Position in the System

```
tender_doc_researcher ──┐ (TD analysis, checklists)
bid_researcher ─────────┤ (bid-vs-TD verification)      → complaint_researcher
oopz_researcher ────────┘ (oopz_decisions precedent DB)     → draft PPOU decision

symmetry: amku_researcher → investigation (bid rigging)
          oopz_researcher → complaint_researcher (complaints)
```

---

## The Argument Is the Unit of Review

A complaint is decomposed into individual arguments; each one is tracked through the entire pipeline:

```
argument:
  claim_verbatim        ← exact quote of the complainant's contention + source (document/page)
  claimed_violation     ← which norm the complainant says was violated
  employer_position     ← verbatim buyer response to THIS argument, or an explicit
                          "buyer provided no explanation on this point"
  type                  ← I / II / III (routing)
  referenced_documents  ← which tender documents the argument concerns
```

Real PPOU decisions answer every contention — the agent is bound to do the same. **Completeness is enforced deterministically:** every extracted argument must end with a verdict proposal, or the run fails (an error, not a warning). No argument can be silently dropped.

---

## Pipeline

| Block | What happens |
|-------|--------------|
| **A — Collection** | Complaint + attached materials + buyer's explanations (Prozorro API); tender context (TD, relevant bids, protocols — only what the complaint touches); document indexing and forced splitting of multi-document files |
| **B — Triage** | Admissibility check (deterministic rules from Art. 18 of Law No. 922: subject matter, deadlines, complainant standing, fee paid); complaint-type classification; argument extraction (verbatim, Gemini) |
| **C — Analysis** | Type-based routing (deterministic): Type I (TD conditions) → challenged TD clause vs. legal norms, adapting `tender_doc_researcher` patterns; Type II (rejection / winner determination) → bid-vs-TD verification on the challenged points, adapting `bid_researcher` patterns (including the composite-document "information, not file" principle); precedent matching against `oopz_decisions` |
| **D — Synthesis (Claude)** | Per-argument evaluation → deterministic completeness check → decision draft in the structure of real PPOU decisions |

An inadmissible complaint is also a valid output — a "leave without review / terminate review" draft with reasoning.

---

## Adversarial by Design

Each argument is not analyzed as "a document review" but as a **weighing of two positions**:

- Complainant's position — verbatim quote + claimed violation
- Buyer's position — verbatim quote from the explanations; if absent, that absence is recorded explicitly (a signal to the specialist, never silently skipped)
- Established facts (verbatim + sources), the applicable norm (exact article/clause), and 1–3 nearest precedents from `oopz_decisions` with the PPOU's verbatim conclusions
- Proposal: **justified / unjustified / outside competence** + confidence level (low confidence is honestly surfaced to the specialist) + draft reasoning text

Precedents support the reasoning — they never replace the analysis. Arguments with no precedents found are flagged as such ("no precedents in the database"), which raises specialist attention rather than blocking the run.

---

## Output

1. **Draft decision (DOCX)** in the structure of real PPOU decisions: introduction → circumstances → parties' positions per argument → reasoning per argument (facts → norm → assessment, with precedent phrasing) → operative part. The operative part is derived from the per-argument verdicts by deterministic aggregation rules.
2. **Analytical memo for the specialist:** a table of argument → proposal → confidence → precedents → attention points (low confidence, missing buyer explanations, no precedents).

---

## Model Routing

| Role | Model |
|------|-------|
| Document description, argument/position extraction, tabular analysis | Gemini 2.5 Flash |
| Argument evaluation (adversarial legal reasoning), decision drafting | Claude (Opus/Sonnet) |
| Admissibility, type routing, completeness checks, first-layer precedent selection | No LLM — deterministic |

---

## The Most Honest Eval in the System

Validation runs on **historical complaints where the PPOU decision already exists**: the agent's draft is compared against the actual decision, argument by argument, on the operative outcome. No synthetic benchmarks, no self-grading — a natural ground truth of thousands of real adjudications.

---

## Scope and Prerequisites

- **MVP covers complaint types I (TD conditions) and II (rejection / winner determination)** — the bulk of real complaints. Type III (other actions/inaction) is honestly marked out-of-scope in the draft.
- No auto-filing, no final decisions — draft for a specialist only.
- Precedents come exclusively from the populated `oopz_decisions` table; the agent does not search the internet for decisions.
- **Critical prerequisite:** mass population of `oopz_decisions` by `oopz_researcher`. Without a filled precedent base, the agent would be "a draft without precedents" — which is why the repair and backfill of `oopz_researcher`'s knowledge-table write path precedes this agent's implementation.

---

## Current State (July 2026)

Architecture and review algorithm fully designed 07.07.2026 (reconstructed from Art. 18 of Law No. 922, CMU Resolution No. 1178, and the structure of real PPOU decisions). No implementation code written yet. Admissibility deadlines will be verified against the current wording of the law at implementation time — wartime rules changed repeatedly, so no deadline numbers are hardcoded into the design.

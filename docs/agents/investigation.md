# 🕵️ Investigation
**Status:** Designed (July 2026), implementation pending — Architecture v2 approved 07.07.2026
**Role:** Main orchestrator agent — investigates anti-competitive concerted actions (bid rigging) across Ukrainian public procurement by following the official AMCU specialist algorithm

---

## Purpose

Ukraine's Law on Protection of Economic Competition, §4 part 2 Art. 6, prohibits anti-competitive concerted actions in procurement (bid rigging). `investigation` is the platform's main orchestrator: it investigates a **case**, not a single tender — the connections between two or more participants across many tenders, files, identifiers, and external sources.

It follows a canonical 49-node algorithm (`ALGORITHM_AMKU.md`), reverse-engineered from the actual procedure AMCU specialists use to prove collusion, and produces a structured conclusion plus a draft submission package.

**Not an analyzer, an investigator:** the unit of work is a case linking participants across procurements, not a single tender's compliance report.

---

## Position in the System

```
oopz_researcher, amku_researcher (knowledge bases)
        ↓
investigation ← THIS AGENT (orchestrator)
        │
        ├── services/participant_search, tender_description, participant_documents
        ├── bid_researcher patterns (document indexing, archive/signature handling)
        └── amku_researcher knowledge (agent_memory.amku_bid_rigging_knowledge) — few-shot for synthesis
        ↓
Draft AMCU submission (conclusion covering 10 mandatory points + evidence matrices)
```

---

## Two-Stage Entry, Three-Phase Pipeline

The algorithm is deliberately **not** a single input→output pipe. It has an explicit scoping checkpoint before deep analysis begins:

| Phase | Trigger | What happens |
|-------|---------|---------------|
| **Phase 0 — Scoping** | Input: subject(s) (EDRPOU/name) or tender ID(s) | Maps all procurements the subjects participated in (individually and jointly), outputs scoping tables to the user. **Checkpoint:** the case waits until the user narrows the scope to specific tenders/subjects. |
| **Phase 1 — Prozorro analysis + requests** | User narrows scope | Downloads tender materials, documents, contracts; runs the full evidence-matrix analysis (Block B below); **in parallel**, sends the first wave of official request letters (Prozorro, tax authority, pension fund) and checks the (open, no-letter-needed) state business registry for participant links |
| **Phase 2 — Response ingestion + synthesis** | Official responses arrive (weeks later) | Ingests IP/email/financial data from institutional responses; synthesizes the final 10-point conclusion |

Between phases, the case "sleeps" — it does not fall through from scoping into deep analysis automatically, and it does not block on institutional responses that haven't arrived yet.

---

## Evidence Matrices (Block B — works entirely from Prozorro data)

For every shared-feature dimension, the agent produces two tables: **all participants** and **shared/common**.

| Dimension | Method |
|-----------|--------|
| File metadata (author, software, creation/print dates) | Deterministic |
| Identical/near-identical submitted documents | Deterministic + LLM |
| Phone numbers, addresses, emails | LLM extraction → tables |
| Shared personnel, equipment (MTB), authorized signatories | LLM extraction + deterministic matching |
| Notary/registration commonalities | LLM + matching |
| Failure to submit critical documents (simulated competition) | LLM + AMCU knowledge-base examples |
| Synchrony of actions (same-day filings, submission timing) | Deterministic |
| Pricing behavior (auction bidding patterns) | Deterministic + LLM |

**Division of labor is a hard architectural rule:** LLMs describe and extract; deterministic code matches, cross-references, builds tables, and routes. This follows directly from a lesson learned auditing `bid_researcher`, `tender_doc_researcher`, and `oopz_researcher` — routing logic left to an LLM was the recurring source of chaos in those systems.

---

## Official Requests (Block C — two-phase by necessity)

Some evidence (IP addresses, email login records, banking activity) does not exist in Prozorro and can only be obtained through official information requests to institutions — a process that takes weeks. The agent generates the request letters immediately after the Phase-0 checkpoint (in parallel with Prozorro-side analysis, not after it) and later ingests the responses once they arrive.

| Requested from | What's requested |
|-----------------|-------------------|
| Prozorro operator, e-procurement platforms | IP addresses / login records for auction and proposal actions |
| Tax authority (ДПС) | IP/email used for tax filings; tax invoice registry (counterparties) |
| Pension fund (ПФУ) | IP/email for portal access |
| Banks | IP/email for banking system logins; financial ties between participants |
| ISPs, telecom operators | Attribution of IP addresses / phone numbers to subscribers |

The state business registry (EDR) is checked in Phase 1 without any letters — it's an open registry, so this evidence dimension doesn't have to wait for Phase 2.

---

## 10-Point Mandatory Conclusion

The final synthesis (Claude, Block D) must address all 10 points — **each one either confirmed present or explicitly documented as absent**. A conclusion cannot silently skip a dimension; this completeness check is enforced by deterministic code, not left to the model's discretion.

1. Shared file metadata
2. Shared (or absent) IP addresses
3. State registry (EDR) links between participants
4. Shared (or absent) physical addresses
5. Shared (or absent) phone numbers
6. Shared (or absent) email addresses
7. Shared features across submitted documents
8. Shared personnel or persons paid by multiple participants
9. Synchrony of actions
10. Pricing/auction-behavior analysis

Every evidentiary claim in the conclusion must trace to a verbatim quote and an exact source (file/field) — the same discipline `amku_researcher` uses when mining AMCU decisions for proof logic.

---

## Model Routing

| Role | Model | Rationale |
|------|-------|-----------|
| Extraction — contacts, personnel, equipment, document descriptions, tabular content analysis | Gemini 2.5 Flash | High call volume, low cost |
| Final synthesis, evidentiary chains, the 10-point conclusion, legal qualification | Claude (Opus/Sonnet) | Complex legal reasoning |
| File properties, synchrony, hashing, matching, completeness checks | No LLM | Determinism, reproducibility, zero hallucination risk |

---

## Reuse Strategy

`investigation` does not rebuild what already works. It calls existing services directly as Python libraries (no subprocess calls, learned from a first-edition antipattern):

| Source | What it provides |
|--------|-------------------|
| `services/participant_search` | All procurements a subject participated in |
| `services/tender_description` | Structured tender descriptions |
| `bid_researcher` patterns | Document indexing, signature scanning, archive extraction (adapted, not the whole agent) |
| `amku_researcher` knowledge base | Evidence patterns and proof/counter-argument logic for the final synthesis (few-shot) |

A first architecture edition was audited and found largely unworkable (subprocess orchestration, mock data, broken imports); select clean modules (legal analyzers, validators, entity extraction) are being carried forward, the rest discarded.

---

## Current State (July 2026)

Architecture v2 is fully designed and cross-checked node-by-node against the source AMCU procedure diagram (49 nodes). No implementation code has been written yet. Scope is deliberately narrow — bid rigging under §4 part 2 Art. 6 only, matching `amku_researcher`'s scope — with automatic institutional API integrations (tax/pension/banking) explicitly out of MVP scope: those bodies don't expose public APIs, so the agent generates request letters and a human ingests the replies.

---

## 💎 Value to the System

`investigation` is the consumer that gives the platform's knowledge-building agents a downstream purpose: `oopz_researcher`'s precedent database informs risk assessment, and `amku_researcher`'s evidence/reasoning base directly trains how `investigation` builds and defends its own bid-rigging case.

# 🔍 TenderDoc Researcher
**Status:** Production v4.0
**Role:** First agent in the pipeline — analyzes tender documentation before bid preparation

---

## Purpose

Automatically downloads tender documentation from ProZorro, extracts text, performs 16-point legal analysis across 13 procurement categories, and generates a structured report for tender participants.

**Output answers the questions:**

- ❓ Is it worth participating in this tender?
- ❓ What violations exist and can they be appealed?
- ❓ What documents need to be prepared?
- ❓ What is the appeal deadline?

---

## Position in the System

```
oopz_researcher (regulatory decisions database)
        ↓ (read-only: tender_doc_researcher reads results)
tender_doc_researcher  ← THIS AGENT
        ↓
bid_researcher (receives document checklist via agent_handoffs)
        ↓
[future agent] participant document preparation
```

---

## Input

`internal_id` — ProZorro system's internal UUID (not the public UA-XXXX number)

---

## 12-Step Pipeline

| Step | Module | Role | Critical |
|------|--------|------|----------|
| 1 | `classifier.py` | CPV code → classification across 13 categories (canonical map, shared with bid_researcher) | ✅ Yes |
| 2 | `registry.py` | Deduplication check | No |
| 3 | `downloader.py` | JSON + tender documents + amendments (latest-version grouping by document id) | ✅ Yes |
| 4 | `file_extractor.py` | Text extraction (docx/pdf/xlsx) | ✅ Yes |
| 5 | `oopz_fetcher.py` | Regulatory decisions by CPV prefix | No |
| 6 | `customer_profiler.py` | Buyer procurement history analysis (stub) | No |
| 7 | `qa_analyzer.py` | Q&A analysis + tender amendments (once per procurement, even with multiple lots) | No |
| 8 | `base_analyzer.py` | 2 LLM calls: checklist + 16-point analysis; branches per active lot if lots present | ✅ Yes |
| 9 | `contract_analyzer.py` | Project contract legal review (once per procurement) | No |
| 10 | `report_formatter.py` | 6 output files generation (per lot if lots present) | No |
| 11 | `registry.py` | Save results + lot-suffixed registry key if applicable | No |
| 12 | `handoff_sender.py` | Handoff to bid_researcher (DB + file-based fallback) | No |

**Multi-lot procurements (implemented 09.07.2026):** if a tender has more than one active lot,
each is analyzed independently — separate `analysis/lot_1/`, `analysis/lot_2/` output, separate
registry entries. Cancelled lots are skipped. Q&A analysis and contract review still run once
per procurement (not per lot).

---

## 16 Analysis Criteria

| # | Criterion | Description |
|---|-----------|-------------|
| 1 | **Document checklist** | Complete checklist of all required documents |
| 2 | **Risk summary** | Overall risk assessment |
| 3 | **Risk impact** | Whether risks block participation |
| 4 | **Legislative violations** | Specific articles, direct quotes from tender documentation |
| 5 | **Competition restrictions** | Conditions that narrow the pool of participants |
| 6 | **Excessive requirements** | Requirements beyond legal necessity |
| 7 | **Unlawful requirements** | Legally prohibited requirements |
| 8 | **Tailoring indicators** | Specification written for a specific supplier |
| 9 | **Deadline analysis** | Submission deadlines, appeal windows |
| 10 | **Bank guarantee requirements** | Size limits (≤0.5% works, ≤3% goods/services) |
| 11 | **Evaluation criteria** | Price weight (≥70% mandatory), non-price criteria |
| 12 | **CPV compliance** | Subject matches declared category |
| 13 | **Localization requirements** | CMU Resolution No. 782, 30% degree, ≥200K UAH threshold |
| 14 | **Technical requirements** | Brand-specific specifications, hidden supplier restrictions |
| 15 | **Rejection grounds** | Formal grounds by which buyer may reject a bid |
| 16 | **Consolidated verdict** | RECOMMENDED / NOT RECOMMENDED + appeal deadline |

**Plus additionally:**
- **Contract analysis** — project contract review (adhesion contract doctrine, Civil Code of Ukraine violations)
- **Winner checklist** — what to do within 4 days of receiving award notification

---

## 13 Procurement Categories

| # | Category | CPV codes |
|---|----------|-----------|
| 1 | Construction works | 45xxxxxx |
| 2 | Maintenance/repair | 45453100, 50xxxxxx |
| 3 | Food products | 15xxxxxx |
| 4 | Pharmaceuticals | 336xxxxx |
| 5 | Medical equipment | 331xxxxx |
| 6 | Utilities and energy | 40, 65xxxxxx |
| 7 | Fuel | 09xxxxxx |
| 8 | Technical goods | 31,32,34,38,42,43xxxxxx |
| 9 | Consumables | 24, 30xxxxxx |
| 10 | IT services | 48, 72xxxxxx |
| 11 | General services | 79, 85, 90xxxxxx |
| 12 | Consulting | 70, 71, 73xxxxxx |
| 13 | Simple goods | 18, 19xxxxxx |

**Canonical routing source (08.07.2026):** `prompts/dk_category_map_canonical.md` — kept in
sync with `bid_researcher`'s own `_CPV_CATEGORY_MAP` by deliberate policy (both files change
together only). The `03` prefix conflict is resolved by splitting on the 3rd digit: `031/032/033`
→ food products, `034` → technical goods (timber/lumber). The `71` prefix (architectural/
engineering services) stays under consulting, compensated by a dedicated sub-block in the
category prompt.

---

## LLM Architecture — Dual-Call Design, Multi-Provider

All LLM calls go through a single `llm_client.call_llm(prompt, role)` entry point (unified
09.07.2026), with the provider selected by `LLM_PROVIDER=gemini|openai|claude`. Gemini is the
provider actually used across production runs; the Claude and OpenAI paths exist and have been
exercised in testing.

Avoids anchoring to few-shot examples by splitting into two independent calls:

| | Call A | Call B |
|---|--------|--------|
| **Purpose** | Document checklist | Deep legal analysis |
| **max_tokens** | 30,000 | 65,000 |
| **Output** | document_blocks | 18 other JSON sections |

**Benchmark results (21 production runs):**

| Task | Best result |
|------|-------------|
| Checklist (Call A) | Run 10: 13 blocks, 57 items |
| Hidden requirements | Up to 13 per tender |
| Contract analysis | 4 violations, 7-9 appeal grounds (stable) |

---

## 🌍 Donor Program Detection

Automatically detects 7 international donor programs and applies additional analysis rules:

| Donor | Detection markers |
|-------|------------------|
| Ukraine Facility | "ukraine facility", "regulation eu 2024/792" |
| EBRD | "єбрр", "ebrd" |
| World Bank | "ibrd", "learn ukraine" |
| EIB | "eib", "ukraine investment framework" |
| KfW | "kfw", "uesf" |
| USAID | "usaid", "tapas" |
| UN Agencies | "unicef", "undp", "unops", "unhcr" |

---

## 📁 Output Files

| File | Purpose | Audience |
|------|---------|----------|
| `analysis.json` | Machine format, 19 sections | System, bid_researcher |
| `analysis_report.docx` | Main legal analysis report | Lawyer, participant |
| `documents_checklist.docx` | Document preparation checklist | Executor |
| `contract_analysis.docx` | Contract legal review | Lawyer |
| `winner_checklist.docx` | Post-win action checklist | Participant team |
| `chronological_checklist.docx` | Same checklist sorted by tender documentation sections | Executor |

---

## ⚖️ Core Legal Framework

Wartime rules (CMU Resolution No. 1178) replace standard Law No. 922-VIII:

| Action | Law No. 922 | CMU Resolution No. 1178 (in effect) |
|--------|-------------|-------------------------------------|
| Appeal deadline | 4 days before deadline | **3 days before deadline** |
| Min. period after amendments | 7 days remaining | **4 days remaining** |
| Appeal after amendments | — | **5 days from publication** |
| Non-amendable provisions | — | **Cannot be appealed** |

**Amendments chain (fixed 09.07.2026):** document versions are grouped by Prozorro document
`id`, keeping only the most recent (`dateModified`); older versions move to
`superseded_documents`. The appeal deadline is computed through a 3-level fallback — new
deadline after amendments → primary deadline from Q&A analysis → direct
`submission_deadline − 3 days` — never silently `null`. The chosen path is recorded in
`deadlines.appeal_deadline_source`.

---

## 🔗 Handoff to bid_researcher

Real contract (v3.1, synchronized 09.07.2026): `handoff_sender.py` upserts a `pending` record
into `agent_memory.agent_handoffs` (`context_data` with `checklist`, `winner_checklist`,
`td_documents_path`, `cpv_code`). If the database write fails, a file-based fallback is written
to `analysis/handoff_pending.json` for manual pickup. Each checklist item carries
`requires_content_verification` / `verification_focus` flags that tell `bid_researcher` which
items need deep content verification (bank guarantee form, Art. 16 qualification thresholds,
technical specification) rather than mere presence checking.

---

## 📊 Production Results

**Benchmark tender:** UA-2025-07-14-001945-a (UAH 212M construction, 57 files)

| Run | Violations | Hidden requirements | Appeal grounds | Duration |
|-----|-----------|---------------------|----------------|----------|
| 10 (best) | 13 | 13 | 13 | 721s |
| 18 | 4 | — | 12 | — |
| Typical | 8-13 | 7-13 | 5-13 | ~12 min |

**Test coverage:** 273 pytest tests green (10.07.2026), including dedicated suites for
multi-lot analysis (22 tests) and the amendments chain (22 tests).

# tender_doc_researcher

**Status:** Production v3.2  
**Role:** First agent in the pipeline — analyzes tender documentation before bid preparation

## Purpose

Automatically downloads tender documentation from Prozorro, extracts text, runs 16-point legal analysis across 13 procurement categories, and generates a structured report for tender participants.

**Output answers:**
- Should we participate in this tender?
- What violations exist and can they be appealed?
- What documents do we need to prepare?
- What is the appeal deadline?

## Position in the System

```
oopz_researcher (regulatory decisions database)
        ↓ (read-only: tender_doc_researcher reads results)
tender_doc_researcher  ← THIS AGENT
        ↓
bid_researcher (receives document checklist via agent_handoffs)
        ↓
[future agent] document preparation for participant
```

## Input

`internal_id` — Prozorro system UUID (not the public `UA-XXXX` number)

## 11-Step Pipeline

| Step | Module | Role | Critical |
|------|--------|------|---------|
| 1 | `classifier.py` | CPV code → 13-category classification | Yes |
| 2 | `registry.py` | Deduplication check | No |
| 3 | `downloader.py` | JSON + tender documents + amendments | Yes |
| 4 | `file_extractor.py` | Text extraction (docx/pdf/xlsx) | Yes |
| 5 | `oopz_fetcher.py` | Regulatory decisions by CPV prefix | No |
| 6 | `customer_profiler.py` | Buyer procurement history | No |
| 7 | `qa_analyzer.py` | Q&A + tender amendments analysis | No |
| 8 | `base_analyzer.py` | **2 LLM calls**: checklist + 16-point analysis | Yes |
| 9 | `contract_analyzer.py` | Project contract legal review | No |
| 10 | `report_formatter.py` | 6 output files generation | No |
| 11 | `registry.py` | Save results + handoff to bid_researcher | No |

## 16 Analysis Criteria

1. **Document list** — complete checklist of all required documents
2. **Risk summary** — overall risk assessment
3. **Risk impact** — whether risks block participation
4. **Legislative violations** — specific articles, direct quotes from TD
5. **Competition restrictions** — conditions narrowing participant pool
6. **Excessive requirements** — beyond legal necessity
7. **Unlawful requirements** — legally prohibited requirements
8. **Tailoring indicators** — specification written for specific supplier
9. **Timeline analysis** — submission deadlines, appeal windows
10. **Bank guarantee requirements** — size limits (≤0.5% works, ≤3% goods/services)
11. **Evaluation criteria** — price weight (≥70% required), non-price criteria
12. **CPV compliance** — subject matches declared category
13. **Localization requirements** — CMU No. 782, 30% degree, ≥200K UAH threshold
14. **Technical requirements** — brand-specific specs, hidden supplier restrictions
15. **Rejection grounds** — formal grounds buyer may use to reject bid
16. **Summary verdict** — RECOMMENDED / NOT RECOMMENDED + appeal deadline

Plus:
- **Contract analysis** — project contract review (adhesion contract doctrine, Civil Code violations)
- **Winner checklist** — what to do within 4 days of winning notification

## 13 Procurement Categories

| # | Category | CPV Codes |
|---|----------|-----------|
| 1 | Construction works | 45xxxxxx |
| 2 | Maintenance/repair | 45453100, 50xxxxxx |
| 3 | Food products | 15xxxxxx |
| 4 | Pharmaceuticals | 336xxxxx |
| 5 | Medical equipment | 331xxxxx |
| 6 | Utilities & energy | 40, 65xxxxxx |
| 7 | Fuel | 09xxxxxx |
| 8 | Technical goods | 31,32,34,38,42,43xxxxxx |
| 9 | Consumables | 24, 30xxxxxx |
| 10 | IT services | 48, 72xxxxxx |
| 11 | General services | 79, 85, 90xxxxxx |
| 12 | Consulting | 70, 71, 73xxxxxx |
| 13 | Simple goods | 18, 19xxxxxx |

## LLM Architecture — Dual-Call Design

Avoids anchoring on few-shot examples by splitting into two independent calls:

| | Call A | Call B |
|-|--------|--------|
| Purpose | Document checklist | Deep legal analysis |
| max_tokens | 30,000 | 65,000 |
| Output | `document_blocks` | 18 other JSON sections |

**Provider benchmarks (21 production runs):**

| Task | Optimal model | Evidence |
|------|--------------|---------|
| Checklist (Call A) | Gemini 2.5 Flash | Run 10: 13 blocks, 57 items |
| Hidden requirements | Gemini 2.5 Flash | Gemini=13 vs GPT=fewer |
| Contract analysis | GPT-5.1 | Runs 12-18: 4 violations, 7-9 appeal grounds |
| Classification | Gemini 3.1 Flash Lite | Fast and cost-effective |

## Donor Program Detection

Automatically detects 7 international donor programs and applies supplemental analysis rules:

| Donor | Detection markers |
|-------|------------------|
| Ukraine Facility | "ukraine facility", "regulation eu 2024/792" |
| EBRD | "єбрр", "ebrd" |
| World Bank | "ibrd", "learn ukraine" |
| EIB | "eib", "ukraine investment framework" |
| KfW | "kfw", "uesf" |
| USAID | "usaid", "tapas" |
| UN agencies | "unicef", "undp", "unops", "unhcr" |

## Output Files

| File | Purpose | Audience |
|------|---------|---------|
| `analysis.json` | Machine format, 19 sections | System, bid_researcher |
| `analysis_report.docx` | Main legal analysis report | Lawyer, participant |
| `documents_checklist.docx` | Document preparation checklist | Executor |
| `contract_analysis.docx` | Contract legal review | Lawyer |
| `winner_checklist.docx` | Post-win action checklist | Participant team |
| `chronological_checklist.docx` | Same checklist sorted by TD section | Executor |

## Key Legal Framework

**Wartime rules (CMU No. 1178) override standard Law No. 922-VIII:**

| Action | Law No. 922 | CMU No. 1178 (active) |
|--------|------------|----------------------|
| Appeal deadline | 4 days before deadline | **3 days** before deadline |
| Min. period after amendments | 7 days remaining | **4 days** remaining |
| Appeal after amendments | — | 5 days from publication |
| Unchanged provisions | — | **Cannot be appealed** |

## Production Results

Reference tender: UA-2025-07-14-001945-a (212M UAH construction, 57 files)

| Run | Provider | Violations | Hidden req. | Appeal grounds | Duration |
|-----|----------|-----------|------------|----------------|---------|
| 10 (best) | Gemini | 13 | 13 | 13 | 721s |
| 18 (best GPT) | GPT-5.1 | 4 | — | 12 | — |
| Typical Gemini | Gemini | 8-13 | 7-13 | 5-13 | ~12 min |

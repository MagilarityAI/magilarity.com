# tender_doc_researcher — Pipeline Source

This directory contains the **bare processing pipeline** of the `tender_doc_researcher` agent — the first agent in the Magilarity multi-agent system.

> **Note:** Prompts are not included in this repository. They represent the core intellectual property of the system and encode years of domain expertise in Ukrainian public procurement law. The pipeline structure and prompt architecture are described below.

---

## What this is

A 14-module Python pipeline that:
1. Takes a ProZorro tender internal ID as input
2. Downloads tender documentation from the ProZorro Public API
3. Extracts text from PDF / DOCX / XLSX files
4. Queries the OOPZ regulatory decisions database for relevant precedents
5. Runs a 16-point legal analysis via LLM
6. Analyzes the draft contract for legal risks
7. Generates structured JSON + 4 DOCX reports
8. Passes the document checklist to `bid_researcher` via the agent handoffs table

Real output examples are in [`/examples`](../../examples/).

---

## Pipeline modules

| File | Role |
|------|------|
| `main.py` | Orchestrator — runs all steps in sequence |
| `classifier.py` | CPV code classification into 13 procurement categories (Sonnet) |
| `downloader.py` | ProZorro API: tender JSON + all TD files + amendments + Q&A |
| `file_extractor.py` | Text extraction: python-docx (primary), pdfplumber, openpyxl |
| `oopz_fetcher.py` | SQL: fetches OOPZ appeal rulings by CPV prefix |
| `customer_profiler.py` | SQL: buyer profile by EDRPOU (partial — full impl. after YouControl integration) |
| `qa_analyzer.py` | Q&A analysis + tender amendments detection (Sonnet) |
| `base_analyzer.py` | Core 16-point legal analysis (Opus) |
| `contract_analyzer.py` | Draft contract legal review — Civil Code, Law 922-VIII, CMU №668 (Opus) |
| `report_formatter.py` | Structures JSON output + generates 4 DOCX reports (Sonnet) |
| `registry.py` | Deduplication check + results registry (JSON + Excel) |
| `handoff_sender.py` | Writes document checklist to `agent_memory.agent_handoffs` for `bid_researcher` |
| `llm_client.py` | Unified LLM client — Claude / Gemini / OpenAI with role-based routing |
| `log_setup.py` | Logging configuration |

---

## Prompt architecture (not included)

The `prompts/` directory is excluded. It contains:

| File | Contents |
|------|----------|
| `base_prompt.py` | 16-point analysis template — the core legal checklist applied to every tender |
| `legal_context.py` | Ukrainian legislation verbatim — Art. 16, 17, 18 of Law 922-VIII; CMU Resolution №1178 (wartime procurement rules); appeal deadlines |
| `contract_analysis.py` | Contract review instructions — Civil Code Art. 634, 849; Law 922-VIII Art. 41; CMU №668 general construction contract conditions |
| `dk_mapping.md` | Full CPV code → 13 category mapping with classification rules (Order №708) |
| `building_works.py` | Category-specific prompt: construction (CC1/CC2/CC3 consequence classes, licensing, subcontracting) |
| `maintenance_works.py` | Category prompt: maintenance and repair works |
| `food_products.py` | Category prompt: food products |
| `pharmaceuticals.py` | Category prompt: pharmaceuticals |
| `medical_equipment.py` | Category prompt: medical equipment |
| `utilities_energy.py` | Category prompt: utilities and energy |
| `fuel.py` | Category prompt: fuel and petroleum products |
| `technical_goods.py` | Category prompt: technically complex goods |
| `consumables.py` | Category prompt: consumables and office supplies |
| `it_services.py` | Category prompt: IT services and software |
| `general_services.py` | Category prompt: general services |
| `consulting_services.py` | Category prompt: consulting services |
| `simple_goods.py` | Category prompt: simple goods |

Each category prompt encodes procurement-specific violation patterns, typical discriminatory requirement structures, and few-shot examples from real OOPZ rulings relevant to that category.

---

## Output

Each analysis produces:

| File | Audience |
|------|----------|
| `analysis.json` | System — 19 structured sections, consumed by `bid_researcher` |
| `analysis_report.docx` | Lawyer / participant — 16-point legal analysis with citations |
| `documents_checklist.docx` | Bid preparation team — full document list with TD quotes |
| `contract_analysis.docx` | Lawyer — contract risk review with appeal deadline |
| `winner_checklist.docx` | Participant team — post-award action checklist |

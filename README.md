# MAGILARITY

**AI-powered multi-agent system for automated legal investigation of Ukrainian public procurement. Analyzes Prozorro tenders, АМКУ decisions, legislative compliance and participant documents using specialized AI agents and LLM orchestration.**

---

## What is MAGILARITY?

MAGILARITY is an intelligent legal investigation platform built for the Ukrainian public procurement market. It automates the detection of violations, collusion, and irregularities in Prozorro tenders using a multi-agent AI architecture.

The system combines document analysis, legislative cross-referencing, and structured reporting to deliver actionable insights for legal professionals, compliance teams, and investigators.

---

## Agents

| Agent | Status | Purpose |
|-------|--------|---------|
| `investigation` | In development | Main orchestrator — coordinates all investigation modules |
| `tender_doc_researcher` | In development | Analyzes tender documentation across 13 procurement categories |
| `bid_researcher` | In development | Analyzes participant bids, technical specs, and compliance |
| `oopz_researcher` | Ready v2.0 | Analyzes АМКУ regulatory decisions |
| `amku_researcher` | Nearly ready | Researches anti-monopoly committee rulings |

---

## Key Capabilities

- **Tender document analysis** — automated review of technical specifications, qualification requirements, and evaluation criteria across 13 ДК021 procurement categories
- **Bid analysis** — comparison of participant proposals against tender requirements, detection of specification tailoring
- **Legislative compliance** — cross-referencing with Ukrainian procurement law and regulatory decisions
- **Participant document processing** — OCR, classification, and AI description of uploaded tender documents
- **Structured reporting** — automated DOCX reports with findings, risk flags, and evidence

---

## Technology Stack

- **AI / LLM** — Claude (Anthropic), Gemini 2.5 Flash (Google), GPT-4o (OpenAI)
- **Backend** — Python, multi-agent orchestration
- **Databases** — PostgreSQL (legislative database — 54 tables), agent memory store
- **Document processing** — OCR (Tesseract), PDF parsing, archive extraction
- **Infrastructure** — Docker, containerized deployment
- **Data source** — Prozorro Public API v2.5

---

## Data Sources

- **Prozorro** — Ukrainian public procurement platform (prozorro.gov.ua)
- **АМКУ** — Anti-Monopoly Committee of Ukraine decisions
- **Verkhovna Rada** — Legislative database (data.rada.gov.ua)
- **Court registers** — Ukrainian court decision databases

---

## Contact

**Website:** [magilarity.com](https://magilarity.com)  
**GitHub:** [github.com/MagilarityAI](https://github.com/MagilarityAI)

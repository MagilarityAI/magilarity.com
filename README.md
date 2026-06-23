# MAGILARITY

**AI-powered multi-agent system for automated legal investigation of Ukrainian public procurement. Analyzes Prozorro tenders, regulatory decisions, legislative compliance and participant documents using specialized AI agents and LLM orchestration.**

---

## The Problem

Ukraine's public procurement system (Prozorro) processes hundreds of thousands of tenders annually. Detecting violations — bid rigging, specification tailoring, collusion, unlawful requirements — requires deep legal expertise, analysis of hundreds of pages of documents, and cross-referencing with regulatory decisions and legislation.

This work currently takes experienced lawyers 8–16 hours per tender. MAGILARITY automates it.

---

## What MAGILARITY Does

The system takes a Prozorro tender ID as input and produces:

- A **legal compliance report** identifying violations of procurement law (Law No. 922-VIII, CMU Resolution No. 1178)
- A **document checklist** for tender participants — every document required, with exact quotes from the tender documentation
- A **bid analysis** — AI review of each participant's submitted documents against the checklist
- A **contract risk analysis** — identifying one-sided conditions, hidden obligations, violations of Civil Code
- An **appeal package** — structured grounds for filing a complaint to the Procurement Appeals Body (ООПЗ)

---

## Architecture — 5 Specialized Agents

```
oopz_researcher ──────────────────────────────────────────────────────────────────────┐
    ↓ (regulatory decisions database)                                                  │
tender_doc_researcher ─────────────────────────────────────────────────────────────────┤
    ↓ (document checklist via agent_handoffs)                                          │
bid_researcher                                                                         │
    ↓ (bid compliance report)                                                          │
investigation (orchestrator) ──────────────────────────── reads all agent outputs ────┘
```

| Agent | Status | Purpose |
|-------|--------|---------|
| `tender_doc_researcher` | Production v3.2 | Full tender document analysis — 16 legal criteria + contract review + 13 procurement categories |
| `bid_researcher` | Production v3.3 | Participant bid analysis — document compliance, technical spec comparison, digital signature verification |
| `oopz_researcher` | Production v2.0 | Analysis of procurement appeals body decisions — builds regulatory precedent database |
| `amku_researcher` | Beta | Anti-Monopoly Committee decision research |
| `investigation` | Active development | Main orchestrator — coordinates all agents for full investigation |

---

## tender_doc_researcher — How It Works

Analyzes tender documentation across **13 procurement categories** (construction, food, pharmaceuticals, IT services, fuel, medical equipment, etc.).

**11-step pipeline:**
1. Classification — identifies CPV code and procurement category
2. Registry check — deduplication
3. Download — full Prozorro JSON + all tender documents
4. Text extraction — python-docx (primary), pdfplumber, openpyxl
5. ООПЗ precedent retrieval — relevant regulatory decisions from database
6. Customer profiling — procurement history analysis
7. Q&A analysis — processes buyer clarifications and tender amendments
8. **Core analysis (2 LLM calls)** — 16-point legal analysis + document checklist
9. Contract analysis — project contract legal review
10. Report generation — 6 output files
11. Registry update + handoff to bid_researcher

**16 analysis criteria include:**
- Legislative violations (Law No. 922-VIII, CMU No. 1178)
- Competition restrictions and discriminatory requirements
- Specification tailoring indicators (designed for a specific supplier)
- Excessive qualification requirements
- Evaluation criteria fairness (price weight ≥70%)
- Localization requirements (CMU No. 782)
- Appeal grounds with deadlines (3 days before submission deadline under martial law)

**Output:** `analysis_report.docx`, `documents_checklist.docx`, `contract_analysis.docx`, `winner_checklist.docx`, `chronological_checklist.docx`, `analysis.json`

---

## bid_researcher — How It Works

Receives the document checklist from `tender_doc_researcher` and analyzes each participant's submitted bid.

**Cascade pipeline (sieve architecture):**
```
Stage 1: File indexing      → 1 Gemini call per file → doc_index.json
Sieve 1: Simple documents   → 1 text call → confirmed / pending
Sieve 2: Tabular documents  → batches of 8 PDFs → confirmed / pending
Sieve 3: Complex scans      → batches of 8 PDFs → confirmed / unresolved
Arbitrator                  → sequential per unresolved doc → final verdict
Final report                → JSON + DOCX
```

**Key capabilities:**
- Detects information within composite documents (legal basis: Art. 16 Law No. 922-VIII)
- Technical specification comparison via GPT-5.1 vision (PDF scans → images)
- Document content verification for bank guarantees, qualification criteria, forms
- Digital signature scanning (`.p7s` files) with inheritance for archive contents
- Incremental analysis — proposal → 24h correction → winner documents
- Archive extraction with bank guarantee package detection

**Verdict scale:** `compliant` → `requires_correction` → `non_compliant` → `requires_user_review`

**Output per participant:** `{edrpou}_analysis.json` (15+ sections), `{edrpou}_report.docx` (15+ chapters, A4 landscape)

---

## oopz_researcher — How It Works

Processes decisions of Ukraine's Procurement Appeals Body (ООПЗ) and builds a searchable regulatory database used by other agents.

**10-step analysis per decision:**
- GPT analysis with strict anti-hallucination rules (all claims must cite decision text)
- Legal validation — all statutory references verified against legislation database
- Hybrid quality scoring (70% LLM + 30% independent validator)
- Grade system: A+ (9-10), A (8-8.9), B+ (7-7.9) ...

**Output:** DOCX detailed report, JSON for agent consumption, Excel registry, PostgreSQL storage in `agent_memory`

---

## Technology Stack

| Layer | Technology |
|-------|-----------|
| **LLM** | Multi-provider: Google, OpenAI, Anthropic — routed by task type |
| **Backend** | Python 3.11, multi-agent orchestration |
| **Document processing** | python-docx, pdfplumber, PyMuPDF (PDF→PNG), openpyxl, Tesseract OCR |
| **Databases** | PostgreSQL — legislation DB (54 tables, ~3.6M documents), agent memory DB |
| **Report generation** | Node.js + docx npm package (DOCX), python-docx |
| **Infrastructure** | Docker, docker-compose, Terraform |
| **Data source** | Prozorro Public API v2.5 |
| **Digital signatures** | asn1crypto (PKCS#7 / `.p7s` parsing) |

---

## Data Sources

| Source | Purpose |
|--------|---------|
| **Prozorro Public API v2.5** | Tender data, participant bids, documents |
| **Verkhovna Rada** (`data.rada.gov.ua`) | Ukrainian legislation database — 340,000+ normative documents |
| **ООПЗ decisions** | Procurement appeals body regulatory database (2000+ decisions) |
| **АМКУ decisions** | Anti-monopoly committee rulings |

---

## Legislation Coverage

The system applies and cross-references:
- **Law No. 922-VIII** "On Public Procurement" — Arts. 16, 17, 18, 22–27, 41
- **CMU Resolution No. 1178** (2022) — Wartime procurement special rules
- **CMU Resolution No. 782** — Localization requirements
- **Civil Code Arts. 634, 841, 849** — Contract law (adhesion contracts, contractor rights)
- **CMU Resolution No. 668** — General conditions for construction contracts

---

## Scale & Performance

- Analyzes a full tender (50+ documents) in 10–15 minutes
- Processes participant bids with 10+ files per participant
- Tested across 21 production tender runs (Run 10: 13 violations, 13 hidden requirements, 13 appeal grounds detected)
- 113/113 tests passing

---

## Phase 1 Roadmap

| Agent | Status | Purpose |
|-------|--------|---------|
| `oopz_researcher` | ✅ Production | ООПЗ decision analysis |
| `tender_doc_researcher` | ✅ Production | Tender document analysis |
| `bid_researcher` | ✅ Production | Bid compliance analysis |
| `amku_researcher` | 🔄 90% complete | Anti-Monopoly Committee decisions |
| `td_generator` | 🔄 Planned | Tender documentation generator using accumulated requirements DB |
| `investigation` | 🔄 Active development | Collusion investigation orchestrator (9 violation types, 4 legal strategies) |
| `bid_doc_preparer` | 🔄 Planned | Participant document package preparation |

**Planned integrations:**
- **YouControl API** — automated verification of tender participants and buyers via Ukrainian corporate registries: beneficial owners, court decisions, financial statements, sanctions screening, license status

---

## Links

**Website:** [magilarity.com](https://magilarity.com)  
**Organization:** [github.com/MagilarityAI](https://github.com/MagilarityAI)

---

## Documentation

- [tender_doc_researcher](docs/agents/tender_doc_researcher.md) — Tender document analysis agent
- [bid_researcher](docs/agents/bid_researcher.md) — Bid compliance analysis agent
- [oopz_researcher](docs/agents/oopz_researcher.md) — Regulatory decisions agent
- [Infrastructure](docs/infrastructure.md) — Technical stack, databases, deployment
- [Roadmap](docs/roadmap.md) — Phase 1 completion plan

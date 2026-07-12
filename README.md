# 🪄 MAGILARITY
## Magical Transparency in Public Procurement through Artificial Intelligence

> *Magilarity = Magic + Clarity — bringing magical transparency where it is deliberately hidden*

**MAGILARITY** is a production-grade multi-agent AI platform for automated legal analysis of Ukraine's public procurement system. The system analyzes ProZorro tenders, regulatory decisions, legislative compliance, and participant documents using specialized AI agents and large language model orchestration.

---

## 🎯 The Problem We Solve

Ukraine's public procurement system (ProZorro) processes hundreds of thousands of tenders annually totaling over **800 billion hryvnias**. Detecting violations — bid rigging, discriminatory tender requirements, specification tailoring for a specific supplier, anti-competitive concerted actions — requires deep legal expertise, analysis of hundreds of pages of documents, and cross-referencing regulatory decisions with legislation.

**This work currently takes an experienced lawyer 8–16 hours per tender.**

### Systemic market problems:

- 🔴 **Hidden discriminatory requirements** — buyers deliberately conceal conditions that restrict competition across various sections of tender documentation
- 🔴 **Specification tailoring** — technical characteristics are written to match only one specific supplier
- 🔴 **Anti-competitive collusion** — participants coordinate prices and bid submission strategies
- 🔴 **One-sided contracts** — draft contracts contain conditions that protect exclusively the buyer's interests
- 🔴 **Inaccessibility of legal help** — small and medium businesses cannot afford a specialized lawyer for every tender

**MAGILARITY automates this entire process.**

---

## 💡 What MAGILARITY Does

The system takes a ProZorro tender number and generates a complete legal analysis:

| Output | Description |
|--------|-------------|
| 📋 **Violation Report** | Legal qualification of violations of Law No. 922-VIII and CMU Resolution No. 1178 with statutory references |
| 📄 **Document Checklist** | Complete checklist of documents for the participant with exact quotes from the tender documentation |
| 🔍 **Bid Analysis** | AI review of each participant's submitted documents against requirements |
| ⚖️ **Contract Analysis** | Detection of one-sided conditions, hidden obligations, Civil Code of Ukraine violations |
| 🏢 **Supplier Research** | Equipment brand/model identification from specs, search for distributors in Ukraine |
| 📝 **Appeal Package** | Structured grounds for filing a complaint to the Procurement Appeals Body (PPOU) with precedent references |

---

## 🤖 Architecture — 8 Agents (3 production, 1 in development, 4 designed)

```
oopz_researcher ──────────────────────────────────────────────┐
    ↓ (appeals body decisions database)                        │
tender_doc_researcher ─────────────────────────────────────────┤
    ↓ (document checklist via agent_handoffs)                  │
bid_researcher                                                  │
    ↓ (bid compliance report)                                  │
investigation (orchestrator) ──── reads all results ───────────┘

amku_researcher → agent_memory.amku_bid_rigging_knowledge → investigation
complaint_researcher (designed) → PPOU complaint review, consumes oopz_researcher's precedent table

BUYER SIDE:       td_creator (designed)  — TD constructor  ←verified by— tender_doc_researcher
PARTICIPANT SIDE: bid_creator (designed) — bid package generator ←verified by— bid_researcher
```

| Agent | Status | Purpose |
|-------|--------|---------|
| [`tender_doc_researcher`](tender_doc_researcher.md) | ✅ Production v4.0 | Full tender documentation analysis — 16 legal criteria + contract review + 13 procurement categories + multi-lot support |
| [`bid_researcher`](bid_researcher.md) | ✅ Production v3.4 | Participant bid analysis — document compliance, technical spec comparison, digital signature verification |
| [`oopz_researcher`](oopz_researcher.md) | ✅ Production v2.0 | PPOU decision analysis — building regulatory precedent database, writes to `oopz_decisions` knowledge table |
| [`amku_researcher`](amku_researcher.md) | 🔄 In development (core repaired) | Anti-Monopoly Committee decision research — builds evidence/reasoning knowledge base for `investigation` |
| [`investigation`](investigation.md) | 🔄 Designed (July 2026) | Main orchestrator — bid-rigging investigations following the AMCU specialist algorithm; implementation pending |
| [`complaint_researcher`](complaint_researcher.md) | 🔄 Designed (July 2026) | PPOU complaint review assistant — drafts decision proposals for a human specialist; implementation pending |
| [`td_creator`](td_creator.md) | 🔄 Designed (July 2026) | Tender documentation constructor for buyers — requirements base + precedent-backed risk warnings; implementation pending |
| [`bid_creator`](bid_creator.md) | 🔄 Designed (July 2026) | Participant bid package generator — profile-driven documents bound verbatim to TD requirements; implementation pending |

**Platform:** [Platform architecture (frontend + backend)](platform.md) — user cabinets for both market sides, FastAPI gateway, task queue, billing, notifications; designed July 2026, implementation pending. Includes the cloud credits usage plan.

---

## 🔬 TenderDoc Researcher — How It Works

Analyzes tender documentation across **13 procurement categories** (construction, food products, pharmaceuticals, IT services, fuel, medical equipment, etc.).

### 11-step pipeline:

1. **Classification** — CPV code and procurement category determination
2. **Registry check** — deduplication
3. **Download** — full ProZorro JSON + all tender documents
4. **Text extraction** — python-docx (primary), pdfplumber, openpyxl
5. **PPOU precedent retrieval** — relevant decisions from the database
6. **Customer profiling** — procurement history analysis
7. **Q&A analysis** — processing buyer clarifications and tender amendments
8. **Core analysis (2 LLM calls)** — 16-point legal analysis + document checklist
9. **Contract analysis** — project contract legal review
10. **Report generation** — 6 output files
11. **Registry update** + handoff to bid_researcher

### 16 analysis criteria include:

- Legislative violations (Law No. 922-VIII, CMU Resolution No. 1178)
- Competition restrictions and discriminatory requirements
- Specification tailoring indicators (designed for a specific supplier)
- Excessive qualification requirements
- Evaluation criteria fairness (price weight ≥70%)
- Localization requirements (CMU Resolution No. 782)
- Appeal grounds with deadlines (3 days before submission deadline under martial law)

### 🌟 Unique Equipment Investigator Module

For specific equipment, the agent automatically:
- Extracts technical specifications from tender documentation
- Identifies the brand and model via web search
- Finds official distributors in Ukraine
- Detects specification tailoring indicators for a specific manufacturer
- Generates a ready-to-submit complaint text for the PPOU

### Donor Program Support

A dedicated module for procurements funded by international donors:
- 🇺🇦 Ukraine Facility (EU)
- 🏦 EBRD, World Bank, EIB
- 🇺🇸 USAID
- 🇺🇳 UN agencies, KfW

**Output files:** `analysis_report.docx`, `documents_checklist.docx`, `contract_analysis.docx`, `winner_checklist.docx`, `chronological_checklist.docx`, `analysis.json`

---

## 📋 Bid Researcher — How It Works

Receives the document checklist from tender_doc_researcher and analyzes each participant's submitted bid.

### Cascade pipeline (sieve architecture):

```
Stage 1: File indexing      → 1 LLM call per file → doc_index.json
Sieve 1: Simple documents   → 1 text call → confirmed / pending
Sieve 2: Tabular documents  → batches of 8 PDFs → confirmed / pending
Sieve 3: Complex scans      → batches of 8 PDFs → confirmed / unresolved
Arbitrator                  → sequential per unresolved → final verdict
Final report                → JSON + DOCX
```

### Key capabilities:

- Detection of information within composite documents (legal basis: Art. 16 of Law No. 922-VIII)
- Technical specification comparison via vision LLM (PDF scans → images)
- Document content verification: bank guarantees, qualification criteria, forms
- Digital signature scanning (.p7s files) with inheritance for archive contents
- Incremental analysis: proposal → 24h correction → winner documents
- **SAFEGUARD mechanism** — protection against LLM errors in bank guarantee analysis

**Verdict scale:** `compliant` → `requires_correction` → `non_compliant` → `requires_user_review`

**Output per participant:** `{edrpou}_analysis.json` (15+ sections), `{edrpou}_report.docx` (15+ chapters, A4 landscape)

---

## ⚖️ OOPZ Researcher — How It Works

Processes decisions of the Procurement Appeals Body (PPOU) and builds a regulatory precedent database used by other agents.

### 10-step analysis per decision:

1. LLM analysis with strict anti-hallucination rules
2. Legal validation — all statutory references verified against the legislation database
3. Hybrid quality scoring (70% LLM + 30% independent validator)

**Grade system:** A+ (9-10), A (8-8.9), B+ (7-7.9)...

**Output:** detailed DOCX report, JSON for agent consumption, Excel registry, PostgreSQL storage

---

## 🗄️ Databases

### Primary DB (appdb)
**57 tables | 332,524+ records**

| Table | Records | Description |
|-------|---------|-------------|
| legislation | 286,634 | Full text of Ukrainian legislation. Auto-updated daily via data.gov.ua API |
| oopz_decisions | 4,402 | Procurement Appeals Body decisions |
| amku_decisions | 87 | Anti-Monopoly Committee of Ukraine decisions |
| court_decisions | — | Court decisions (table ready, population planned) |
| prozorro_* | — | Real-time ProZorro procurement data |

### Agent Memory DB (magilarity_agent_memory)
**29 tables | 963 records**

| Table | Records | Description |
|-------|---------|-------------|
| agents_registry | 8 | Registered AI agents |
| investigation_cycles | 103 | Completed analysis cycles |
| investigation_steps | 589 | Step-level execution logs |
| learning_experiences | 19 | Agent learning records |
| knowledge_base | 56 | Accumulated knowledge |

---

## 🏗️ Technology Stack

| Layer | Technology |
|-------|-----------|
| LLM | Multi-provider: Google, OpenAI, Anthropic — routed by task type |
| Backend | Python 3.11, multi-agent orchestration |
| Document processing | python-docx, pdfplumber, PyMuPDF (PDF→PNG), openpyxl, Tesseract OCR |
| Databases | PostgreSQL — legislation DB (286,634 documents), agent memory DB |
| Report generation | Node.js + docx npm package (DOCX), python-docx |
| Infrastructure | Docker, docker-compose, Terraform |
| Data source | ProZorro Public API v2.5 |
| Digital signatures | asn1crypto (PKCS#7 / .p7s parsing) |

---

## 📊 Market

- **ProZorro Ukraine:** 800+ billion UAH annual procurement volume
- **200,000+** active procurement participants
- **30,000+** buyers (government agencies, municipal enterprises, hospitals, schools)
- **EU market:** €2 trillion annually (unified public procurement directive)

**The system scales to any jurisdiction with public procurement.**

---

## 🔮 Roadmap

- [x] TenderDoc Researcher v4.0 — tender documentation analysis (multi-lot, amendments chain)
- [x] Bid Researcher v3.4 — participant bid analysis
- [x] OOPZ Researcher v2.0 — appeals body decision research (writes to knowledge table)
- [x] AMKU Researcher — core pipeline repaired, knowledge base builder in development
- [x] ProZorro API integration
- [x] Legislation database (286,634 documents, auto-updated)
- [x] investigation — architecture v2 designed (code not started) → [description](investigation.md)
- [x] complaint_researcher — designed (PPOU complaint review support) → [description](complaint_researcher.md)
- [x] td_creator — TD constructor for buyers, designed July 2026 → [description](td_creator.md)
- [x] bid_creator — participant package generator, designed July 2026 → [description](bid_creator.md)
- [x] Platform architecture (frontend + backend) — designed July 2026, implementation pending → [description](platform.md)
- [ ] Frontend / User dashboard — implementation
- [ ] YouControl API integration
- [ ] Expansion to Polish market
- [ ] Vector database for semantic search

---

## 💼 Founder

**Oleksii Fuzyk**
Practicing public procurement lawyer, Ukraine
10+ years in Ukrainian public procurement
Specialization: protection of economic competition, commercial law, corporate law, and public procurement advisory

*Built entirely with Claude and Claude Code*
*Zero prior programming experience → production-ready platform in 6 months*

---

## 📧 Contact

**Email:** info@magilarity.com
**Website:** magilarity.com

---

*© 2025-2026 Magilarity. Magical transparency in public procurement.*

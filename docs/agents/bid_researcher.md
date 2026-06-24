# 📋 Bid Researcher
**Status:** Production v3.3
**Role:** Second agent in the pipeline — analyzes participant bids for compliance with tender requirements

---

## Purpose

Receives the document checklist from tender_doc_researcher, then downloads, indexes, and analyzes every document submitted by every tender participant. Generates a legal compliance report per participant.

---

## Position in the System

```
tender_doc_researcher → (checklist via agent_handoffs) → bid_researcher ← THIS AGENT
                                                                 ↓
                                                    compliance report per participant
```

⚠️ **Critical dependency:** Cannot operate without a checklist from tender_doc_researcher. If the agent_handoffs record is missing — the pipeline stops with an error.

---

## Cascade Sieve Architecture

```
checklist_receiver   → reads checklist + winner_checklist + path to tender documents
        ↓
bid_loader           → downloads PDF/DOCX/.p7s/archives from ProZorro API
                       classifies files by phase: proposal / correction_24h / winner
        ↓
extract_archives     → unpacks .zip/.rar/.7z; maps archive→contents
                       Bank guarantee packages → separate folder with BG001_ prefix
        ↓
office_converter     → converts DOCX→PDF, XLSX→CSV
        ↓
stage1_indexer       → 1 LLM call per file → doc_index.json
        ↓
correction_analyzer  → analyzes 24h correction documents
        ↓
winner_doc_analyzer  → indexes winner phase documents
        ↓
doc_compliance_verifier → DEEP content verification
                       Coverage: bank guarantees (form compliance),
                       Art. 16 criteria, qualification thresholds
        ↓
techspec_comparator  → FULL technical specification comparison
                       Vision LLM (reads PDF scans as images)
                       Buyer's specification = reference standard; participant's
                       specification extracted verbatim
        ↓
sieve1_simple        → 1 text call → confirmed / pending
        ↓
sieve2_tabular       → batches of 8 PDFs + category routing
        ↓
sieve3_scans         → batches of 8 PDFs + sieve 3 context
        ↓
arbitrator           → sequential per unresolved document → ✅ / ❌ / ⚠️
        ↓
final_report         → 1 LLM call (synthesis) → analysis.json
        ↓
_enrich_final_analysis → deterministic enrichment (no AI):
                       • technical specs from TechSpecComparator
                       • SAFEGUARD for bank guarantees
                       • archive↔content linking
        ↓
signature_scanner    → scans .p7s files → digital_signatures
                       Signature inheritance: archive/Office signatures
                       propagate to contents
        ↓
report_generator     → validation → Node.js generate_docx.js → JSON + DOCX
        ↓
db_manager           → bid_documents + bid_analysis (UPSERT)
```

---

## ⚖️ Core Legal Principle — Information vs. Document

The agent verifies the **presence of information**, not a specific file:

| Match type | Meaning |
|-----------|---------|
| `direct` | Separate dedicated file |
| `composite` | Information contained within another document |
| `no_match` | Information absent |

**Legal basis:** Art. 16 §1, 3, 4 and Art. 26 §1 of Law No. 922-VIII; §43 of CMU Resolution No. 1178; AMCU precedent — a buyer cannot reject a bid if the information is contained in a composite document.

---

## 📅 Document Phases

Every downloaded file is classified by publication date relative to tender deadlines:

| Phase | Date range | Folder |
|-------|-----------|--------|
| `proposal` | ≤ tenderPeriod.endDate | proposal_documents/ |
| `correction_24h` | endDate < date ≤ awards[0].date | 24h_documents/ |
| `winner` | date > awards[0].date | winner_4day_documents/ |
| `signing` | after appeal deadline | signing_documents/ |

---

## 🔍 Technical Specification Comparison (Vision LLM)

For technical goods and construction:

```
PDF pages → PNG images (PyMuPDF)
Buyer's specification from tender documentation = reference standard
Participant's specification extracted verbatim from scanned documents
Detects: deviations, added items, omissions
Output: technical_specs_compliance[] with severity (critical / substantial)
```

---

## 🔎 Document Content Verification (Analysis LLM)

Deep verification of documents where presence alone is insufficient:

**Always verified:**
- Bank guarantee (form compliance per tender annex)
- Art. 16 qualification criteria (experience/similar contracts, equipment, personnel, financial capacity — threshold verification)
- Technical specification

Activated by the `requires_content_verification: true` flag set by tender_doc_researcher for each checklist item.

---

## 📊 Verdict Scale

| Verdict | Meaning | Recommended action |
|---------|---------|-------------------|
| `compliant` | All requirements met | Accept for evaluation |
| `requires_correction` | Correctable deficiencies | Grant 24h (§43 CMU 1178) |
| `non_compliant` | Critical deficiencies | Reject (§44 CMU 1178) |
| `requires_user_review` | Unresolvable or auto-corrected | Manual review |
| `mixed` | Both correctable and critical | Detailed analysis required |

---

## 🛡️ Automated Protection Mechanisms (No AI — Deterministic)

**SAFEGUARD Bank Guarantee:** If an empty placeholder is selected instead of a real bank guarantee → item is escalated to `requires_user_review`. Prevents false rejection.

**TechSpec Escalation:** If technical specification comparison or audit detects deviations → a `compliant` item is escalated to `requires_user_review` (flag: `techspec_escalated`). One-way only — a stricter status is never softened.

---

## ✍️ Digital Signature Analysis

- .p7s file parsing (PKCS#7 via asn1crypto)
- Detects signer name, organization, key type (QES/AES)
- **Signature inheritance:** archive signature propagates to all extracted contents; original Office signature propagates to converted PDF (field: `signed_via`)

---

## 🔄 Incremental Analysis

Designed for staged document publication in ProZorro:

```
Run 1: proposal documents → Report v1
Run 2: 24h correction documents added → Report v2
Run 3: winner documents added → Report v3
```

Files already on disk are not re-downloaded. New Stage 1 files automatically invalidate sieve checkpoints.

---

## 📁 Output File Structure

```
bid_researcher/procurements/{public_id}/{edrpou}_{org_form}_{name}/
    ├── proposal_documents/           ← P001_*.pdf + .p7s signatures
    ├── 24h_documents/                ← C001_*.pdf (corrections)
    ├── winner_4day_documents/        ← W001_*.pdf
    ├── signing_documents/            ← S001_*.pdf
    │   └── _bg_package/              ← BG package (signing phase)
    ├── proposal_documents/_bg_package/ ← BG package (proposal)
    └── checkpoints/
        ├── {edrpou}_file_phases.json
        ├── {edrpou}_correction_results.json
        ├── {edrpou}_winner_doc_results.json
        ├── {edrpou}_techspec_results.json
        └── {edrpou}_analysis_journal.json

bid_researcher/procurements/{public_id}/analysis/
    ├── {edrpou}_analysis.json    ← full JSON 15+ sections
    └── {edrpou}_report.docx      ← DOCX report 15+ chapters (A4 landscape)
```

---

## 📄 DOCX Report Structure (15+ chapters)

| # | Chapter | Condition |
|---|---------|-----------|
| 0 | Header (tender, participant, price, key dates, auction table) | Always |
| 1 | Statistics (5 metric cards) | Always |
| 2 | Executive summary (verdict for buyer + analytics) | Always |
| 3 | Compliance table (7 columns, strikethrough for corrected items) | Always |
| 3a | Bank guarantee analysis (form compliance vs. tender annex) | If BG present |
| 3b | Buyer assessment (24h notice with deficiency text) | If issued |
| 3c | Correction documents (resolved/unresolved per item) | If corrections exist |
| 4 | Technical specifications (deviations, added items, audit notes) | If tech spec exists |
| 5 | Personnel and equipment matrix | If present |
| 6 | Document validity periods | Always |
| 7 | Composite documents | If present |
| 8 | Additional documents | If present |
| 8a | Full document list (all files with type and summary) | Always |
| 9 | Winner documents (award phase) | If present |
| 9a | Winner document checklist results | If present |
| 9b | Contract signing documents | If present |
| 10 | Analytics block | Always |
| 11 | Legal block (for buyer + for analyst) | Always |
| 12 | Digital signatures (including inherited) | If present |
| — | Footer (disclaimer + pipeline statistics) | Always |

---

## 🏷️ Checklist Item Status Codes

| Code | Meaning |
|------|---------|
| **C** | Compliant — document present and meets requirements |
| **24** | 24h correction — present but correctable deficiency |
| **R** | Rejected — critical non-compliance |
| **CR** | Conditional review — requires user verification |
| **M** | Missing — document or information not submitted |

# bid_researcher

**Status:** Production v3.3  
**Role:** Second agent in the pipeline — analyzes participant bids against tender requirements

## Purpose

Receives the document checklist from `tender_doc_researcher` and downloads, indexes, and analyzes every document submitted by each tender participant. Produces a legal compliance report per participant.

## Position in the System

```
tender_doc_researcher → (checklist via agent_handoffs) → bid_researcher ← THIS AGENT
                                                                 ↓
                                                    compliance report per participant
```

**Critical dependency:** Cannot run without a checklist from `tender_doc_researcher`. If `agent_handoffs` record is missing — pipeline stops with error.

## Cascade Sieve Architecture

```
checklist_receiver   → reads checklist + winner_checklist + td_documents_path
        ↓
bid_loader           → downloads PDF/DOCX/.p7s/archives from Prozorro API
                       classifies files by phase: proposal / correction_24h / winner
        ↓
extract_archives     → extracts .zip/.rar/.7z; maps archive→contents
                       Bank guarantee packages → separate folder with BG001_ prefix
        ↓
office_converter     → converts DOCX→PDF, XLSX→CSV (Gemini requires PDF/CSV)
        ↓
[STEP 4] stage1_indexer → 1 Gemini call per file → doc_index.json
        ↓
[STEP 4c] correction_analyzer → analyzes 24h correction documents
        ↓
[STEP 4d] winner_doc_analyzer → indexes winner phase documents
        ↓
[STEP 4e] doc_compliance_verifier → DEEP content verification
                       Model: Gemini 2.5 Flash
                       Scope: bank guarantees (form compliance), Art.16 criteria,
                       qualification thresholds
        ↓
[STEP 4e] techspec_comparator → FULL technical spec comparison
                       Model: GPT-5.1 (vision, reads PDF scans as images)
                       Buyer's spec = ground truth; participant's spec extracted verbatim
        ↓
[SIEVE 1] sieve1_simple → 1 text call → confirmed / pending
        ↓
[SIEVE 2] sieve2_tabular → batches of 8 PDFs + category routing
        ↓
[SIEVE 3] sieve3_scans → batches of 8 PDFs + sieve3 context
        ↓
arbitrator → sequential per unresolved document → ✅ / ❌ / ⚠️
        ↓
final_report → 1 Gemini call (synthesis) → analysis.json
        ↓
_enrich_final_analysis → deterministic enrichment (no AI):
                       • technical_specs from TechSpecComparator
                       • SAFEGUARD for bank guarantees (prevents false rejections)
                       • archive↔contents linking
        ↓
signature_scanner → scans .p7s files → digital_signatures
                    Signature inheritance: archive/Office signatures propagate to contents
        ↓
report_generator → validate → Node.js generate_docx.js → JSON + DOCX
        ↓
db_manager → bid_documents + bid_analysis (UPSERT)
```

## Key Legal Principle — Information vs. Document

The agent checks for **information presence**, not a specific file:

| match_type | Meaning |
|-----------|---------|
| `direct` | Separate dedicated file |
| `composite` | Information within another document |
| `no_match` | Information absent |

**Legal basis:** Art. 16 para. 1, 3, 4 and Art. 26 para. 1 of Law No. 922-VIII; Para. 43 of CMU Resolution No. 1178; АМКУ precedent — buyer cannot reject if information exists within a composite document.

## Document Phases

Each downloaded file is classified by publication date relative to tender timeline:

| Phase | Date range | Folder |
|-------|-----------|--------|
| `proposal` | ≤ tenderPeriod.endDate | `документи_пропозиції/` |
| `correction_24h` | endDate < date ≤ awards[0].date | `документи_24_години/` |
| `winner` | date > awards[0].date | `документи_переможця_4_дні/` |
| `signing` | after complaint period | `документи_підписання/` |

## Technical Specification Comparison (GPT-5.1)

For technical goods and construction:
- PDF pages → PNG images (PyMuPDF)
- Buyer's spec from tender documentation = ground truth
- Participant's spec extracted verbatim from scanned documents
- Detects: deviations, added clauses, omissions
- Result: `technical_specs_compliance[]` with severity (`critical` / `substantial`)

## Document Content Verification (Gemini 2.5 Flash)

Deep verification for documents where presence alone is insufficient:

**Always verified:**
- Bank guarantee (form compliance per tender appendix)
- Art. 16 qualification criteria (experience/analogous contracts, equipment, personnel, financial capacity — threshold verification)
- Technical specification

**Triggered by:** `requires_content_verification: true` flag set by `tender_doc_researcher` per checklist item.

## Verdict Scale

| Verdict | Meaning | Recommended action |
|---------|---------|-------------------|
| `compliant` | All requirements met | Accept for evaluation |
| `requires_correction` | Correctable deficiencies | Grant 24h (Para. 43 CMU 1178) |
| `non_compliant` | Critical deficiencies | Reject (Para. 44 CMU 1178) |
| `requires_user_review` | Unresolvable or autocorrected | Manual review |
| `mixed` | Both correctable and critical | Detailed analysis needed |

## Automatic Safeguards (No AI — Deterministic)

**SAFEGUARD Bank Guarantee:** If empty placeholder selected instead of real bank guarantee → item escalated to `requires_user_review`. Prevents false rejection.

**TechSpec Escalation:** If technical comparison or audit found deviations → compliant item escalated to `requires_user_review` (flag: `techspec_escalated`). Only upward (stricter status not softened).

## Digital Signature Analysis

- Parses `.p7s` files (PKCS#7 via `asn1crypto`)
- Detects signer name, organization, key type (КЕП/УЕП)
- **Signature inheritance:** archive signature propagates to all extracted contents; Office original signature propagates to converted PDF (field: `signed_via`)

## Incremental Analysis

Designed for Prozorro's phased document publication:

- **Run 1:** proposal documents → Report v1
- **Run 2:** 24h correction documents added → Report v2
- **Run 3:** winner documents added → Report v3

Files already on disk are not re-downloaded. New Stage 1 files automatically invalidate sieve checkpoints.

## Output Files

```
bid_researcher/закупівлі/{public_id}/{edrpou}_{legal_form}_{name}/
    ├── документи_пропозиції/        ← P001_*.pdf + .p7s signatures
    ├── документи_24_години/         ← C001_*.pdf (corrections)
    ├── документи_переможця_4_дні/   ← W001_*.pdf
    ├── документи_підписання/        ← S001_*.pdf
    │   └── _пакет_БГ/               ← bank guarantee package (signing phase)
    ├── документи_пропозиції/_пакет_БГ/ ← bank guarantee package (proposal)
    └── checkpoints/
        ├── {edrpou}_file_phases.json
        ├── {edrpou}_correction_results.json
        ├── {edrpou}_winner_doc_results.json
        ├── {edrpou}_techspec_results.json
        └── {edrpou}_analysis_journal.json

bid_researcher/закупівлі/{public_id}/analysis/
    ├── {edrpou}_analysis.json   ← 15+ sections full JSON
    └── {edrpou}_report.docx     ← 15+ chapter DOCX report (A4 landscape)
```

## DOCX Report Structure (15+ chapters)

| # | Chapter | Condition |
|---|---------|-----------|
| 0 | Header (tender, participant, price, key dates, auction table) | Always |
| 1 | Statistics (5 metric cards) | Always |
| 2 | Executive summary (verdict for buyer + analyst) | Always |
| 3 | Compliance table (7 columns, strikethrough for corrected items) | Always |
| 3a | Bank guarantee analysis (form compliance vs. TD appendix) | If BG present |
| 3b | Buyer evaluation (24h notices with deficiency text) | If issued |
| 3c | Correction documents (resolved/unresolved per item) | If corrections exist |
| 4 | Technical specifications (deviations, added clauses, audit notes) | If tech spec exists |
| 5 | Personnel and equipment matrix | If present |
| 6 | Document validity periods | Always |
| 7 | Composite documents | If present |
| 8 | Extra documents | If present |
| 8a | Complete document list (all files with type and summary) | Always |
| 9 | Winner documents (award phase) | If present |
| 9a | Winner document checklist results | If present |
| 9b | Contract signing documents | If present |
| 10 | Analytics block | Always |
| 11 | Legal block (for buyer + for analyst) | Always |
| 12 | Digital signatures (including inherited) | If present |
| — | Footer (disclaimer + pipeline stats) | Always |

## Checklist Item Status Codes

| Code | Meaning |
|------|---------|
| `В` | Compliant — document present and meets requirements |
| `24` | 24h correction — present but correctable deficiency |
| `В!` | Deviation — critical non-compliance |
| `УК` | Conditional — requires user verification |
| `ВД` | Absent — document or information not submitted |

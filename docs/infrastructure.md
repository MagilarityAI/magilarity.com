# Infrastructure

## Deployment

The system runs in Docker containers managed via docker-compose. Terraform provisions cloud infrastructure.

```
docker-compose up --build
```

## Databases

### APPDB (`appdb`) — Read-only
Legislative database for the Ukrainian jurisdiction.

| Contents | Scale |
|----------|-------|
| Ukrainian legislation full text | ~3.6M documents |
| ООПЗ decisions | 2,000+ decisions |
| АМКУ decisions | Indexed |
| Court decisions | Indexed |
| Law No. 922-VIII articles | Full text |
| CMU Resolution No. 1178 | Full text |

54 tables. Agents have read-only access. All legal cross-referencing and validation queries run against this database.

### Agent Memory (`magilarity_agent_memory`) — Read/Write
Agent coordination and results storage.

Schema: `agent_memory`

| Table | Purpose |
|-------|---------|
| `investigation_cycles` | Analysis run tracking |
| `investigation_steps` | Step-level execution log |
| `agent_handoffs` | Inter-agent data transfer (checklist → bid_researcher) |
| `investigation_insights` | Extracted patterns and insights |
| `equipment_identifications` | Cached equipment brand identifications |
| `ua_suppliers` | Ukrainian supplier cache |

### Prozorro Intel (`prozorro_intel`) — Read/Write
Tender index and analysis results.

| Table | Purpose |
|-------|---------|
| `prozorro_index` | Tender public_id ↔ internal_id mapping |
| `tenders` | Analysis results per tender |
| `tender_lots` | Lot-level analysis |
| `tender_participants` | Participant registry |
| `bid_documents` | Participant document index |
| `bid_analysis` | Bid compliance results |
| `td_requirements` | Tender requirement database (for TD generator) |

## CI/CD

GitHub Actions pipeline:
- `flake8` linting
- `black` formatting check
- `mypy` type checking
- `pytest` test suite
- Docker image build and push

## Document Processing Pipeline

```
Input: PDF / DOCX / XLSX / archives
    ↓
Archive extraction (.zip / .rar / .7z)
    ↓
Office conversion: DOCX→PDF (Word COM / docx2pdf), XLSX→CSV (openpyxl)
    ↓
Text extraction: python-docx (primary), pdfplumber, openpyxl
    ↓
OCR fallback: Tesseract (for scanned PDFs)
    ↓
PDF→PNG: PyMuPDF/fitz (for GPT-5.1 vision calls)
    ↓
LLM analysis
    ↓
Output: JSON + DOCX reports
```

## Report Generation

DOCX reports are generated via Node.js (`docx` npm package) for advanced formatting:
- A4 landscape format, Arial 11pt, 0.5" margins
- Color-coded tables, strikethrough for superseded items
- Automatic section headers, page breaks

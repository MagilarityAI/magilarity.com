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

## AI Models

| Model | Provider | Role |
|-------|----------|------|
| `gemini-2.5-flash` | Google | Primary analysis — tender docs, contract review |
| `gemini-3.1-flash-lite` | Google | Document indexing, fast classification |
| `gpt-5.1` | OpenAI | Technical specification comparison (vision, PDF scans) |
| `claude-opus-4-7` | Anthropic | Tender analysis (alternative provider) |
| `claude-sonnet-4-6` | Anthropic | Classification, report structuring |

## Environment Variables

```bash
# LLM providers
LLM_PROVIDER=gemini          # gemini | openai | claude
GEMINI_API_KEY=...           # for classification role
GEMINI_API_KEY_2=...         # for analysis role (separate quota)
OPENAI_API_KEY=...           # for GPT-5.1 technical spec comparison
ANTHROPIC_API_KEY=...        # for Claude provider

# Databases
POSTGRES_DB=appdb
POSTGRES_USER=...
POSTGRES_PASSWORD=...

MEMORY_DB_NAME=magilarity_agent_memory
MEMORY_DB_HOST=localhost
MEMORY_DB_PORT=5432
MEMORY_DB_USER=...
MEMORY_DB_PASSWORD=...

TENDERS_DB_NAME=prozorro_intel
TENDERS_DB_HOST=localhost
TENDERS_DB_PORT=5432
```

## Rate Limits & Performance

| Provider | Tier | Limits | Notes |
|----------|------|--------|-------|
| Gemini | Free | 250K TPM, 10 RPM, 250 RPD | ~62 full analyses/day |
| Gemini | Paid | Higher | Target for production |
| GPT-5.1 | Paid | Per token | Used only for tech spec comparison |

Retry logic: exponential backoff, up to 13 attempts. 503 from Gemini detected by string matching (not exception type).

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

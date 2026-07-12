# 🏗️ Magilarity Infrastructure

---

## Deployment

The system runs in Docker containers managed via docker-compose. Terraform provisions cloud infrastructure.

```bash
docker-compose up --build
```

---

## 🗄️ Databases

### APPDB (appdb) — Read-Only (one write exception)

Legislative database for the Ukrainian jurisdiction.

| Contents | Scale |
|----------|-------|
| Ukrainian legislation full text | 286,634 normative documents |
| PPOU decisions | 4,400+ decisions |
| AMCU decisions | Indexed |
| Court decisions | Table ready, population planned |
| Law No. 922-VIII articles | Full text |
| CMU Resolution No. 1178 | Full text |

**54 tables.** Agents have read-only access, with **one deliberate exception**: `oopz_researcher`
writes to `oopz_decisions` (its own knowledge table, step 10.5 of its pipeline, added
07.07.2026) — this is the single write path into APPDB granted to any agent. All other legal
cross-referencing and validation queries run read-only against this database.

**Auto-update:** daily synchronization with data.gov.ua API — new normative documents are downloaded automatically.

---

### Agent Memory (magilarity_agent_memory) — Read/Write

Agent coordination and results storage.

**Schema:** agent_memory

| Table | Purpose |
|-------|---------|
| `investigation_cycles` | Analysis run tracking |
| `investigation_steps` | Step-level execution log |
| `agent_handoffs` | Inter-agent data transfer (checklist → bid_researcher) |
| `investigation_insights` | Extracted patterns and insights |
| `equipment_identifications` | Equipment brand identification cache |
| `ua_suppliers` | Ukrainian supplier cache |
| `learning_experiences` | Agent learning records |
| `knowledge_base` | Accumulated system knowledge |
| `agents_registry` | Active agents registry (8 agents) |
| `amku_bid_rigging_knowledge` | AMCU bid-rigging evidence/reasoning knowledge base (added 07.07.2026, written by `amku_researcher`, read by `investigation`) |

---

### ProZorro Intel (prozorro_intel) — Read/Write

Tender index and analysis results.

| Table | Purpose |
|-------|---------|
| `prozorro_index` | Tender public_id ↔ internal_id mapping |
| `tenders` | Analysis results per tender |
| `tender_lots` | Lot-level analysis |
| `tender_participants` | Participant registry |
| `bid_documents` | Participant document index |
| `bid_analysis` | Bid compliance results |
| `td_requirements` | Tender requirements database (for TD generator) |

---

## ⚙️ CI/CD Pipeline

GitHub Actions pipeline:
- `flake8` — code style check
- `black` — formatting check
- `mypy` — type checking
- `pytest` — test suite
- Docker image build and push

---

## 📄 Document Processing Pipeline

```
Input: PDF / DOCX / XLSX / archives
    ↓
Archive extraction (.zip / .rar / .7z)
    ↓
Office conversion: DOCX→PDF, XLSX→CSV (openpyxl)
    ↓
Text extraction: python-docx (primary), pdfplumber, openpyxl
    ↓
PDF → Markdown: conversion with LLM artifact correction
(50-70% token savings vs. raw PDF)
    ↓
OCR fallback: Tesseract (for scanned PDFs)
    ↓
PDF→PNG: PyMuPDF/fitz (for vision LLM calls)
    ↓
LLM analysis (hybrid model routing)
    ↓
Output: JSON + DOCX reports
```

---

## 📊 Report Generation

DOCX reports generated via Node.js (`docx` npm package) for advanced formatting:
- A4 landscape format, Arial 11pt, 0.5" margins
- Color-coded tables, strikethrough for superseded items
- Automatic section headers, page breaks

---

## 🔀 Hybrid LLM Routing

Different models for different tasks — optimal quality/cost balance:

| Task | Model | Reason |
|------|-------|--------|
| CPV classification | Gemini 2.5 Flash | Speed, low cost |
| File indexing | Gemini 3.1 Flash Lite | Minimum cost |
| Core legal analysis | Claude Opus 4.8 / Sonnet 4.6 | Maximum accuracy |
| Technical spec comparison | GPT-5.1 vision | Reads PDF scans as images |
| PPOU decision analysis | GPT-5.1 | Complex legal reasoning |
| Final report synthesis | Gemini 2.5 Flash | Structured output |

---

## 🔐 Security

- API keys stored in `.env` files (not in code)
- Agents have minimum required database permissions
- APPDB — read-only for all agents
- All operations audited via investigation_steps

---

## 🔐 User Security and System Protection

### User Access Security

**Authentication and authorization:**
- Short-lived JWT tokens (access token 15 min, refresh token 7 days)
- Two-factor authentication (2FA) for all accounts
- Role-Based Access Control (RBAC) — permission separation by role:
  - `participant` — procurement participant (tender documentation analysis, bid verification)
  - `buyer` — contracting authority (TD generator, participant bid analysis)
  - `lawyer` — law firm (extended access, API)
  - `admin` — platform administrator
- Brute force protection — lockout after 5 failed login attempts
- Sessions with automatic timeout on inactivity

**User data protection:**
- Passwords stored exclusively as bcrypt hashes
- Personal data encrypted at-rest (AES-256)
- Data transfer exclusively via HTTPS/TLS 1.3
- Data isolation between clients (tenant isolation)

---

### API and Request Security

**Rate limiting:**
- Per-user request rate limiting
- Separate limits for different operation types:
  - Tender documentation analysis: max 50 requests/day on basic plan
  - API calls: token limits depending on plan
- DDoS protection via Cloudflare

**Input validation:**
- All input parameters verified (tender number, EDRPOU code, etc.)
- SQL injection protection (parameterized queries)
- Uploaded file sanitization
- File size limits for uploads

---

### Infrastructure Protection

**Network security:**
- All components in private network (VPC)
- Database access only from internal network (no public IP)
- Firewall rules — only required ports open
- VPN for administrative access

**Container security:**
- Docker images based on minimal base images (alpine)
- Regular dependency and security patch updates
- Image vulnerability scanning (Trivy / Snyk)
- Containers run as non-root user
- Read-only filesystem where possible

**Secrets and configuration:**
- API keys and passwords stored in `.env` files (not in code)
- In production — Google Secret Manager or HashiCorp Vault
- Scheduled API key rotation
- `.gitignore` — all secrets excluded from repository

---

### Database Security

**Access rights (principle of least privilege):**
- APPDB (legislation) — `SELECT` only for all agents
- agent_memory — `SELECT/INSERT/UPDATE` only for authorized agents
- prozorro_intel — segregated access between agents
- Separate database user per service

**Backups:**
- Automated daily backups of all databases
- Backup storage in separate geographic region
- Monthly backup restoration verification
- Point-in-time recovery for critical databases

---

### Security Audit and Monitoring

**Logging:**
- All user actions logged (login, requests, downloads)
- Logs retained for minimum 90 days
- Centralized log aggregation (ELK Stack or Cloud Logging)
- Administrative action audit trail

**Incident notifications:**
- Alerting on suspicious activity (unusual login time, high request volume)
- Notifications on unauthorized access attempts
- Configuration file integrity monitoring
- Automatic blocking of suspicious IP addresses

---

### Legal Data Protection

Since the system processes legally significant information:

- **Analysis result immutability** — all reports carry a timestamp and content hash
- **Analysis versioning** — full history of all analysis versions per tender is retained
- **Disclaimer** — all reports include a legal disclaimer (the system is an analytical tool, not a substitute for legal advice)
- **Client data confidentiality** — one client's data is inaccessible to others
- **GDPR compliance** — right to erasure, right to data portability

---

## 🔮 Planned Infrastructure

### Vector Database — Semantic Search

Transition from SQL to hybrid SQL + vector search approach:

```
CURRENT APPROACH (SQL):
SELECT * FROM oopz_decisions
WHERE dk_code LIKE '45%'
→ Exact search by CPV code

FUTURE APPROACH (Vector + SQL):
Semantic query: "discriminatory experience
requirements in construction tenders"
→ Finds relevant PPOU decisions
  even when exact words don't match
→ Significantly higher precedent quality
```

**Planned vector databases:**
- `pgvector` (PostgreSQL extension) — no separate server needed
- Or `Qdrant` / `Weaviate` at scale
- Embeddings for: PPOU decisions, legislation articles, benchmark analyses

**When to migrate:** after accumulating 10,000+ analyzed PPOU decisions — semantic search will then provide substantial advantage over exact SQL.

---

### Local Specialized LLM

Fine-tuning an open-source model on Magilarity data:

```
Fine-tuning (QLoRA) on:
├── 286K legislation documents
├── 20K+ PPOU decisions
├── AMCU and court decisions
└── Magilarity benchmark analyses
        ↓
Magilarity Legal Model v1.0
→ Understands Ukrainian procurement law
→ Knows PPOU and AMCU practice
→ Runs locally without API costs
→ Confidential deployment for government clients
```

**Benefits:**
- Independence from external API providers
- Zero marginal inference costs
- Full model control
- Local deployment for clients with confidentiality requirements
- Cannot be replicated without the same unique training data

---

### Infrastructure Scaling

**Current state:** monolithic Docker on a single server

**Next stage (as load grows):**

```
Load Balancer
    ↓
┌─────────────────────────────────┐
│ API Gateway (FastAPI)           │
└──────────┬──────────────────────┘
           ↓
┌──────────────────────────────────────┐
│ Task Queue (Celery + Redis)          │
│ Async tender processing              │
└──────┬───────────────────────────────┘
       ↓
┌──────────────────────────────────┐
│ Agent Pool (Docker Swarm/K8s)   │
│ Horizontal scaling               │
└──────┬───────────────────────────┘
       ↓
┌──────────────────────────────────┐
│ PostgreSQL cluster               │
│ Read replicas for APPDB          │
└──────────────────────────────────┘
```

**Cloud infrastructure (Google Cloud):**
- Cloud Run — agent autoscaling
- Cloud SQL — managed PostgreSQL
- Vertex AI — unified access to AI models
- Cloud Storage — document and report storage
- BigQuery — analytics across 50,000+ ProZorro participants

---

### Monitoring and Analytics

**Planned:**
- Grafana dashboard — pipeline metrics (execution time, API cost, output quality)
- Alerting — notifications on agent errors
- Cost tracking — spend by model and tender
- Quality metrics — output accuracy vs. benchmark cases

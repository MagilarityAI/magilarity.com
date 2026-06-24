# 🗺️ Magilarity Roadmap

---

## ✅ Phase 1 — Production Agents (Complete)

| Agent | Status | Purpose |
|-------|--------|---------|
| `oopz_researcher` | ✅ v2.0 | PPOU decision analysis — building regulatory precedent database |
| `tender_doc_researcher` | ✅ v3.2 | Tender documentation analysis — 16 legal criteria, 13 categories |
| `bid_researcher` | ✅ v3.3 | Bid compliance analysis — document verification, tech spec comparison |

---

## 🔄 In Development — Phase 1 Completion

### amku_researcher (90% complete)
Research and analysis of Anti-Monopoly Committee of Ukraine (AMCU) decisions on anti-competitive concerted actions in public procurement.

---

### td_generator — Tender Documentation Generator
Generates compliant tender documentation using the requirements database accumulated from tender_doc_researcher analyses. The database records which requirements are used in which procurement categories, creating a data-driven template system.

**Data source:** `prozorro_intel.td_requirements` table — automatically populated during each tender_doc_researcher run:
- Requirement text
- CPV category
- Usage count across tenders
- Whether the requirement is legally permissible

---

### investigation — Collusion Investigation Orchestrator
Full 10-stage pipeline for detecting procurement violations:

| Stage | Analysis |
|-------|----------|
| 1-3 | Tender identification, participant analysis |
| 4 | Decision point: violation indicators detected? |
| 5 | Deep analysis: IP correlation, submission timing, metadata |
| 6 | Financial connections, bank guarantee sequences |
| 7 | Document technical analysis: identical errors, shared templates |
| 8 | Financial analysis: price patterns, financial ties |
| 9 | Decision point: sufficient evidence? |
| 10 | Evidence synthesis → AMCU complaint package |

**9 violation categories:**
- Price fixing (price coordination, winner rotation)
- Technical coordination (identical specifications, shared errors)
- Market division (geographic/category allocation)
- Participant discrimination (unlawful barriers)
- Conflict of interest (buyer affiliation)
- Sham competition (shell participants)
- Document manipulation (falsification)
- Deadline violations
- Other procedural violations

**4 legal strategies:** Aggressive (30-50% success), Moderate (50-70%), Conservative (70-85%), Settlement (85-95%)

---

### bid_doc_preparer — Participant Document Package Preparation
Prepares complete document packages for tender participants based on:
- Checklist from tender_doc_researcher
- Document templates
- Participant's existing document archive

---

### YouControl API Integration
Integration with YouControl — Ukraine's corporate information platform — for automated verification of tender participants and buyers:

| Data type | Purpose |
|-----------|---------|
| Company registration data | EDRPOU verification, legal status, registration date |
| Beneficial owners | Conflict of interest detection, affiliated companies |
| Court decisions | Legal history identification, debt disputes |
| Financial statements | Financial capacity claim verification |
| License and permit status | Qualification requirement verification |
| Sanctions screening | Verification of absence from Russian sanctions lists |

**Used by:** `investigation` (participant screening), `bid_researcher` (buyer profiling), `tender_doc_researcher` (customer_profiler module)

---

## 🚀 Phase 2 — Ukraine Market Scaling

### Platform Feature Expansion

**Full customer_profiler — Buyer Profile**
- Buyer reputation rating based on PPOU decisions, court cases, and procurement statistics
- Detection of abuse patterns for specific buyers
- Buyer behavior prediction for new tenders
- Categorization: trusted / caution / high_risk

**PPOU Complaint Review Agent**
- AI assistant for PPOU collegium members during complaint review
- Automatic search for analogous precedents
- Draft operative and reasoning parts of the decision
- Ensuring consistency of PPOU practice

**Automated PPOU Complaint Submission**
- Full complaint package generation based on tender_doc_researcher analysis
- Automatic form filling
- Review status tracking

**Web Interface and User Dashboard**
- Streamlit → full React frontend
- Personal account with analysis history
- Analytics dashboard for law firms
- Third-party integration API

---

### Database Expansion

**Court Decisions Database**
- Administrative court decisions where AMCU is a party
- Supreme Court of Ukraine procurement decisions
- Cross-references with PPOU practice

**Local Specialized LLM**
- Fine-tuning an open-source model on the Ukrainian legal corpus:
  - 286K+ Ukrainian legislation documents
  - 20K+ PPOU decisions
  - AMCU and court decisions
  - Magilarity benchmark analyses
- Independence from external API providers
- Local deployment for clients with confidentiality requirements

---

## 🏛️ Phase 3 — All Ukrainian E-Procurement

### Expansion to All Digital State Trading Platforms

```
UKRAINE STATE TRADING — full coverage:
│
├── PUBLIC PROCUREMENT
│   └── ProZorro ✅ (already integrated)
│       └── ~15 accredited platforms
│
├── BANK ASSET SALES
│   └── Deposit Guarantee Fund (DGF)
│       └── Sale of liquidated bank assets
│
├── SEIZED AND CONFISCATED ASSETS
│   └── ARMA (Asset Recovery and Management Agency)
│       └── Sale of seized property
│
├── PRIVATIZATION AND LEASE
│   └── Prozorro.sale (SFPU)
│       └── State property privatization and lease
│
└── SPECIAL AUCTIONS
    └── Prozorro.sale SAFE
        └── Sale of sanctioned assets
```

**Dedicated agents for each platform:**
- **DGF Agent** — bank asset lot analysis, legal purity check, purchase risk assessment
- **ARMA Agent** — seized asset analysis, criminal proceeding verification, asset return risk
- **Prozorro.sale Agent** — state property privatization and lease condition analysis

---

### State Registry Integration

| Registry | Purpose in the system |
|----------|----------------------|
| **YouControl API** | Corporate info, connections, finances ✅ planned |
| **Unified State Registry** | Legal entity and sole trader verification |
| **Court Decisions Registry** | Court practice on procurement |
| **Real Estate Registry** | Asset verification for DGF/ARMA procurements |
| **NSDC Sanctions Registry** | Participant sanctions screening |
| **NACP Registry** | Conflict of interest verification |
| **State Audit Service** | Buyer audit results |
| **data.gov.ua** | Legislation ✅ already integrated |

---

### B2G Direction — Government Agencies as Clients

**Target partners:**
- **AMCU** — anti-competitive action investigation module
- **State Audit Service** — automated procurement monitoring
- **NACP** — conflict of interest detection
- **Transparency International Ukraine** — anti-corruption monitoring
- **City councils and regional administrations** — own procurement analysis

---

## 🌍 Phase 4 — European Market Entry

### Why Magilarity's Logic Transfers to the EU

```
EU Directive 2014/24 on public procurement
applies across all 27 EU member states

Shared logic for all:
├── Public procurement through unified platforms
├── Anti-competitive concerted actions (Art. 102 TFEU)
├── Appeals bodies (analogous to PPOU)
├── Anti-monopoly committees (analogous to AMCU)
└── Open procurement data

= Agent architecture transfers
  only language and local legislation change
```

### Priority Markets

**🇵🇱 Poland — first EU market**
- Largest public procurement market in CEE (~€50B/year)
- Similar procurement corruption issues
- Large Ukrainian diaspora as early adopters
- Platform: Platforma e-Zamówienia (ProZorro analogue)
- Appeals body: KIO (PPOU analogue)
- Localization timeline: 1-2 months

**🇷🇴 Romania**
- Active procurement market (~€15B/year)
- Significant transparency issues
- Platform: SEAP
- High interest from anti-corruption organizations

**🇧🇬 Bulgaria**
- Similar systemic procurement issues
- Active civil anti-corruption community

**🇩🇪 Germany — long-term target**
- Largest EU procurement market (~€500B/year)
- Platforms: DTVP, Vergabe24
- Requires full localization and a local partner

### EU Entry Strategy

```
STEP 1 — Technical preparation:
├── Language localization (Polish)
├── Polish legislation database loading
└── Polish procurement platform API connection

STEP 2 — Partnership:
├── Law firm partner in Poland
├── Anti-corruption NGO as anchor client
└── CEE accelerator (Startup Wise Guys, EIT Digital)

STEP 3 — Pilot:
├── 10-20 Polish procurement participant companies
├── Output quality verification by local lawyer
└── Prompt adaptation for Polish legal practice

STEP 4 — Scaling:
└── Romania → Bulgaria → other EU countries
```

---

## 💎 Strategic Vision

> *Magilarity — to become the de facto standard for public procurement analysis in Central and Eastern Europe. As YouControl became the standard for counterparty verification in Ukraine — Magilarity will become the standard for working with public procurement.*

**Long-term goal:** An infrastructure platform serving all participants in the public procurement ecosystem — from small businesses entering their first tender to anti-corruption agencies investigating systemic abuses.

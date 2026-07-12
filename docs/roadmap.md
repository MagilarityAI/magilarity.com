# 🗺️ Magilarity Roadmap

---

## ✅ Phase 1 — Production Agents (Complete, with 06–10.07.2026 repair pass)

| Agent | Status | Purpose |
|-------|--------|---------|
| `oopz_researcher` | ✅ v2.0 (repaired 07-08.07.2026) | PPOU decision analysis — building regulatory precedent database; now actually writes to its own knowledge table (`oopz_decisions`, previously a dead link), 125 tests |
| `tender_doc_researcher` | ✅ v4.0 (repaired 09.07.2026) | Tender documentation analysis — 16 legal criteria, 13 categories, multi-lot support, working amendments chain, 273 tests |
| `bid_researcher` | ✅ v3.4 (routing fixes 10.07.2026) | Bid compliance analysis — document verification, tech spec comparison, 326 tests |

A June 2026 audit found that several of these production agents had components documented as
working but not actually wired into the pipeline (e.g. oopz_researcher's knowledge table write
was a dead link on both ends). The 06–10.07.2026 session repaired all four agents below against
that audit; test suites listed above reflect the post-repair regression baseline.

---

## 🔄 In Development — Phase 1 Completion

### amku_researcher (core pipeline repaired 07.07.2026)
Research and analysis of Anti-Monopoly Committee of Ukraine (AMCU) decisions on anti-competitive concerted actions in public procurement. Full-text Gemini 2.5 analysis, prompt v2 (evidence + respondents' objections + AMCU's refutation + norms), dedicated knowledge table `amku_bid_rigging_knowledge`, 70 tests. Remaining before "complete": live validation of prompt v2 on real decisions, then mass backfill — this blocks `investigation`'s few-shot synthesis.

---

### complaint_researcher — designed, not started
Sixth agent: reviews PPOU complaints and drafts a decision proposal for a human specialist
(the argument is the unit of evaluation; natural eval set = historical complaints).
Architecture designed 07.07.2026. Precondition: `oopz_researcher` repair (complete as of
08.07.2026) — this agent consumes the same knowledge table.

---

### td_creator — Tender Documentation Builder for Public Buyers (designed 10.07.2026)
The first agent serving the BUYER side: procurement type → category's baseline requirements
(auto-checked by frequency) → optional requirements with LIVE risk warnings (precedents
from real PPOU rulings + safer wording suggestions) → parameters with category medians /
safe ranges → draft tender documentation (Word) + cover note. The normative skeleton is
the officially approved model TD form plus category-specific regulations. Two modes: from
scratch / from the buyer's own draft. Generated TD gets a self-check by our own analyzer
(tender_doc_researcher) — "through the eyes of a bidder and a complainant" before publication.

**Requirements base:** populated by mass processing of real TDs (lightweight Gemini
extraction mode) + as a by-product of every tender_doc_researcher run; requirements are
stored canonically (frequencies, parameters, risk profiles linked to the PPOU rulings
base). UI — Streamlit MVP.

---

### investigation — Collusion Investigation Orchestrator
**Status:** architecture v2 designed 07.07.2026, cross-checked node-by-node against the drawio
diagram (Phase 0 scoping checkpoint, early requirements, EDR lookup moved to Phase 1). Code not
yet started. Depends on `amku_researcher`'s knowledge table being populated (few-shot source
for synthesis) and on `oopz_researcher`'s precedent table (both now structurally ready after
the 06–10.07.2026 repair pass).

Architecture v2 follows the official AMCU case officer's methodology (verified node-by-node
against the evidentiary flow diagram) and runs in three phases:

| Phase | Content |
|-------|---------|
| Phase 0 — Scoping | tender universe of the subjects → summary tables → checkpoint: the case officer narrows the investigation scope |
| Phase 1 — Prozorro analysis | matrices of shared traits across participants: file properties, upload timing, identical/duplicate documents, contact details, shared staff/equipment, synchronized actions, pricing behavior + generation of the official information request package (tax authority / pension fund / banks / marketplaces) |
| Phase 2 — Authority responses | ingestion of official responses (IP addresses, e-mails, financial links) → final synthesis |

**The conclusion covers 10 mandatory points** (each one: presence OR substantiated absence
of the trait; completeness is enforced deterministically — no point can be silently
skipped) → draft AMCU submission. Every piece of evidence is a verbatim quote with an
exact source. MVP scope — bid rigging only (Art. 6(2)(4) of the Law of Ukraine "On
Protection of Economic Competition").

---

### bid_creator — Bid Document Package Generator for Participants (designed 10.07.2026)
The eighth agent, mirroring td_creator on the supplier side: generates the bid document
package from the tender_doc_researcher requirements checklist. Simple documents
(certificates, guarantee letters, consents) — generated fully, each one verbatim-anchored
to the specific TD requirement it satisfies; complex ones (technical specifications, bank
guarantee) — honestly "the user's responsibility" with maximum assistance (a bank
application pre-filled with TD parameters, "where to obtain" checklists). Organization
profile with a permanent document vault and expiry tracking; style variability + a
mandatory disclaimer; phase packages following the tender chronology (24-hour correction
regeneration driven by the bid_researcher report, winner documents with deadlines,
contract signing). Independent self-check of the generated package by the bid_researcher
verifier. Multi-tenant for external users. UI — Streamlit MVP.

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

**PPOU Complaint Review Agent** — see `complaint_researcher` in Phase 1 above (designed
07.07.2026; this item covers its evolution into a full collegium tool once the precedent
base is populated).

**Automated PPOU Complaint Submission**
- Full complaint package generation based on tender_doc_researcher analysis
- Automatic form filling
- Review status tracking

**Platform: User Cabinets + Backend (DESIGNED 11-12.07.2026)**
- Two user types: PARTICIPANT (cabinet: entry from a tender number, phase-driven journey —
  analysis → package → 24-hour window → award → contract) and BUYER (TD builder: entry
  from a procurement type, step-by-step wizard) — full screen concepts + live HTML mockups ready
- Shared backend: FastAPI + task queue for long-running analyses + auth + billing
  (subscriptions with quotas + metered premium actions) + Telegram notifications
  (deadlines, buyer's mandatory actions, "your result is ready")
- Strategy: everything on Streamlit first → full frontend later via the same APIs
- Internal tooling: knowledge-base operator console (review desk, batch processing with
  budget control), news & weekly appeal-statistics module with a PPOU practice-shift detector

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

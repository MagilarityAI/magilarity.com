# Roadmap — Phase 1

## Production Agents (Complete)

| Agent | Status | Purpose |
|-------|--------|---------|
| `oopz_researcher` | ✅ v2.0 | ООПЗ decision analysis — builds regulatory precedent database |
| `tender_doc_researcher` | ✅ v3.2 | Tender documentation analysis — 16 legal criteria, 13 categories |
| `bid_researcher` | ✅ v3.3 | Bid compliance analysis — document verification, tech spec comparison |

## In Development

| Agent | Status | Purpose |
|-------|--------|---------|
| `amku_researcher` | 🔄 90% | Anti-Monopoly Committee decision research and analysis |
| `td_generator` | 🔄 Planned | Tender documentation generator — uses requirements database built from processed tenders |
| `investigation` | 🔄 Active | Collusion investigation orchestrator — coordinates all agents, detects bid rigging |
| `bid_doc_preparer` | 🔄 Planned | Document package preparation and generation for tender participants |

## Phase 1 Completion Plan

### td_generator (Tender Documentation Generator)
Generates compliant tender documentation using the requirements database accumulated from `tender_doc_researcher` analysis runs. The database records which requirements are used in which procurement categories, creating a data-driven template system.

**Data source:** `prozorro_intel.td_requirements` table — populated automatically during each `tender_doc_researcher` run with:
- Requirement text
- CPV category
- Occurrence count across tenders
- Whether it's legally selectable

### investigation (Collusion Investigation Orchestrator)
Full 10-stage investigation pipeline for detecting procurement violations:

| Stage | Analysis |
|-------|---------|
| 1-3 | Tender identification, participant analysis |
| 4 | Decision point: violation indicators detected? |
| 5 | Deep analysis: IP correlation, submission timing, metadata |
| 6 | Financial connections, bank guarantee sequences |
| 7 | Document technical analysis: identical errors, shared templates |
| 8 | Financial analysis: pricing patterns, financial links |
| 9 | Decision point: sufficient evidence? |
| 10 | Evidence synthesis → АМКУ complaint package |

**9 violation categories:**
1. Price collusion (coordinated pricing, winner rotation)
2. Technical coordination (identical specs, shared errors)
3. Market division (geographic/category splits)
4. Participant discrimination (unlawful barriers)
5. Conflict of interest (buyer affiliation)
6. Sham competition (dummy participants)
7. Document manipulation (falsification)
8. Deadline violations
9. Other procedural violations

**4 legal strategies:** Aggressive (30-50% success), Moderate (50-70%), Conservative (70-85%), Settlement (85-95%)

### bid_doc_preparer
Prepares complete document packages for tender participants based on:
- Checklist from `tender_doc_researcher`
- Document templates
- Participant's existing document archive

### YouControl API Integration
Integration with YouControl — Ukraine's corporate information platform — for automated verification of tender participants and buyers:

| Data type | Purpose |
|-----------|---------|
| Company registration data | Verify ЄДРПОУ, legal status, registration date |
| Beneficial owners | Detect conflicts of interest, affiliated companies |
| Court decisions | Identify litigation history, debt disputes |
| Financial statements | Verify financial capacity claims |
| License and permit status | Check qualification requirements |
| Sanctions screening | Verify absence of Russian sanctions |

**Used by:** `investigation` agent (participant screening), `bid_researcher` (buyer profiling), `tender_doc_researcher` (customer_profiler module)

## Phase 2 (Future)

- Full `customer_profiler` — buyer reputation scoring based on ООПЗ decisions, court cases, and procurement statistics
- Streamlit web interface for human-in-the-loop review
- API for third-party integrations
- Automated ООПЗ complaint filing

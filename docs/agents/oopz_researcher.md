# oopz_researcher

**Status:** Production v2.0  
**Role:** Processes ООПЗ (Procurement Appeals Body) decisions and builds the regulatory precedent database

## Purpose

Ukraine's Procurement Appeals Body (ООПЗ) issues decisions on procurement complaints. These decisions form the primary regulatory precedent for what is and isn't lawful in tenders.

`oopz_researcher` processes these decisions and stores structured analysis in the database, which `tender_doc_researcher` queries when analyzing new tenders.

## Position in the System

```
oopz_researcher ← THIS AGENT
        ↓
    oopz_decisions table (appdb)
        ↓ (read by)
tender_doc_researcher → uses precedents when analyzing new tenders
```

## 10-Step Analysis per Decision

| Step | Action |
|------|--------|
| 1 | Create investigation cycle in `investigation_cycles` |
| 2 | Load and validate decision text |
| 3 | **LLM analysis** — extract all facts, positions, reasoning |
| 4 | Extract metadata from LLM result |
| 5 | **Quality scoring** — hybrid: 70% LLM + 30% validator |
| 6 | **Legal validation** — verify all legal references against legislation DB |
| 7 | Create output folder (YEAR/MONTH/PROCUREMENT_ID) |
| 8 | Generate reports (DOCX + JSON + metadata) |
| 9 | Update Excel registries (2 files with dynamic columns) |
| 10 | Save to `agent_memory` database |

## Anti-Hallucination System — Two Factors

**Factor 1 (LLM analysis):**  
The model is prohibited from inventing facts. Every claim must be supported by a direct quote from the decision text.

**Factor 2 (Legal validation):**  
All statutory references are verified against the full Ukrainian legislation database (~340,000 normative documents in `appdb`). References to non-existent articles are flagged.

## Quality Scoring

| Component | Weight | What it checks |
|-----------|--------|----------------|
| LLM self-assessment | 70% | Completeness, reasoning quality |
| Independent validator | 30% | Citations, logic, legal compliance, structure |

**Grade scale:**
- **A+** (9.0–10.0) — Outstanding
- **A** (8.0–8.9) — Excellent  
- **B+** (7.0–7.9) — Good
- **B** (6.0–6.9) — Satisfactory
- **C** (5.0–5.9) — Low quality
- **D** (<5.0) — Unsatisfactory

## DOCX Report Structure

1. **Header** — Decision number, date
2. **Parties** — Complainant, buyer, other parties
3. **Procurement subject** — Tender information
4. **Event chronology** — Evidence by category
5. **Legal positions** ⭐ (most important section)
   - 5.1 Complainant's position + legal basis
   - 5.2 Buyer's counterarguments
   - 5.3 **ООПЗ decision** — reasoning, key questions, logic, legal norms applied
6. **Decision outcome** — Result, justification, consequences
7. **Legal analysis** — Violations found, principles, validation
8. **Systemic conclusions** — Precedent value, red flags, recommendations
9. **Analysis metadata**

## Database Output

Decisions are stored in `agent_memory` with full structured data and are also indexed in `appdb.oopz_decisions` for retrieval by other agents:

```sql
-- How tender_doc_researcher queries this data:
SELECT decision_number, dk_code, complaint_type, key_violation, analysis_json
FROM oopz_decisions
WHERE dk_code LIKE '45%'    -- CPV prefix for construction
  AND is_analyzed = true
ORDER BY importance_score DESC
LIMIT 5
```

## Scale

- 2,000+ ООПЗ decisions available for processing
- Each decision processed in ~30 seconds
- Batch processing supported (full 2,000 decision corpus)

## Output Files per Decision

```
output/oopz_decisions/YEAR/MONTH/PROCUREMENT_ID/
├── analysis.json              ← Structured analysis for agents
├── metadata.json              ← Decision metadata
├── detailed_report_{N}.docx   ← Full DOCX report for human review
├── decision_original.pdf      ← Original decision file
└── README.txt                 ← Description

output/oopz_decisions/
├── decisions_registry.xlsx    ← Main Excel registry (dynamic columns)

modules/legislation_checker/oopz_decisions/
└── {ID}_DECISION_NUMBER.json  ← Training data for other agents
```

## Value to Other Agents

`oopz_researcher` is the **foundation** of the MAGILARITY ecosystem:

| Agent | How it uses ООПЗ data |
|-------|----------------------|
| `tender_doc_researcher` | Retrieves relevant precedents by CPV code to inform analysis |
| `bid_researcher` | References АМКУ practice on composite document acceptance |
| `investigation` | Uses violation patterns for collusion investigation |

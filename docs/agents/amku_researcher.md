# ⚔️ AMKU Researcher
**Status:** In development (core pipeline works, awaiting live validation + mass population)
**Role:** Builds the evidence-and-reasoning knowledge base for the `investigation` agent from AMCU decisions on bid rigging

---

## Purpose

Ukraine's Anti-Monopoly Committee (AMCU) issues decisions on anti-competitive concerted actions in public procurement (bid rigging). `amku_researcher` reads these decisions and extracts not just facts, but the **reasoning logic** AMCU specialists use to prove collusion — including respondents' objections and how AMCU refutes them.

**Scope is deliberately narrow — by design, not limitation:** only §4 part 2 Art. 6 of the Law of Ukraine "On Protection of Economic Competition" (anti-competitive concerted actions / bid rigging). The agent is meant to go deep on this one violation type, not expand to other AMCU matters.

`amku_researcher` does not judge the decisions — AMCU's conclusions are already final. Its job is to mine the evidence patterns and proof logic so `investigation` can apply the same reasoning when building new cases.

---

## Position in the System

```
input/*.pdf|docx (AMCU decisions)
        ↓
amku_researcher ← THIS AGENT
        ↓
    agent_memory.amku_bid_rigging_knowledge
        ↓ (read by)
investigation → uses evidence patterns and proof logic for collusion investigations
```

---

## Pipeline

```
main.py (regex metadata extraction: decision number, date, parties)
        ↓
analyze_decision.py
    → LLM: Gemini 2.5 Flash, full-text (whole decision in one call, no chunking)
    → fallback: OpenAI, via LLM_PROVIDER
        ↓
validate.py (structure check on LLM response)
        ↓
result JSON v2
   ├── agents_docs/amku_research_results/ (local JSON/DOCX/Excel reports)
   └── amku_memory_store.py → agent_memory.amku_bid_rigging_knowledge (agent_id='amku_researcher')
```

**Full-text analysis (repaired 07.07.2026):** the previous architecture chunked decisions before analysis, which lost cross-references between evidence and conclusions. The current pipeline sends the entire decision text to Gemini 2.5 Flash in a single call.

---

## What the Knowledge Table Captures (Prompt v2, 07.07.2026)

Each analyzed decision contributes:

| Element | Description |
|---------|-------------|
| Evidence (`докази`) | Direct quotes classified by strength |
| Logical chains | Argument sequences with legal norms attached at each link |
| Respondents' objections | What the accused parties argued in their defense |
| AMCU's refutation | How the committee dismantled each objection |
| Fines with justification | Penalty amounts and AMCU's stated rationale (within §4 part 2 Art. 6 scope only) |

This combination — evidence + counter-argument + refutation — is what makes the table useful as training material for `investigation`, which will need to anticipate and pre-empt the same objections when building its own cases.

---

## 🛡️ Anti-Hallucination Rules

- Every evidentiary claim must trace to a direct quote from the decision text.
- Legal norms are extracted **as stated in the decision** — a "photograph" of AMCU's own reasoning. No independent legal validation is performed (deliberate decision: AMCU decisions are already final; validation belongs in agents that apply norms anew, primarily `investigation`).
- Decision date not found → left empty + warning. Never defaults to today's date.

---

## 🗄️ Database Output

```sql
-- agent_memory.amku_bid_rigging_knowledge (agent_id = 'amku_researcher')
-- UPSERT logic in amku_memory_store.py; does not raise on failure (caller pipeline continues)
```

Read-only sources: `appdb.legislation`, `appdb.amku_decisions` (87 decisions indexed).

---

## 📈 Current State (10.07.2026)

- Core analysis chain (Gemini full-text + prompt v2 + validate + memory store): built and tested.
- 70 tests green (34 core analysis + 36 knowledge-store).
- Database cleanup completed 07.07.2026 — knowledge table reset to a clean state (0 rows) after removing legacy chunking-era records and cross-contamination from another agent's writes.
- **Blocking `investigation`'s few-shot synthesis:** the knowledge table needs both (1) live validation of prompt v2 on 1-2 real decisions (paid LLM calls, pending user go-ahead) and (2) mass backfill of the remaining AMCU decisions once validated.

---

## 💎 Value to Other Agents

| Agent | How it uses AMCU data |
|-------|------------------------|
| `investigation` | Draws on evidence patterns and proof/counter-argument logic when synthesizing a collusion case for submission to AMCU |

Unlike `oopz_researcher`'s precedent database (used for broad tender-risk lookups), this table is purpose-built for one downstream consumer: teaching `investigation` how AMCU specialists actually prove — and defend — a bid-rigging finding.

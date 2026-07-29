# CLAUDE.md - Technical Notes for LLM Council

This file contains technical details, architectural decisions, and important implementation notes for future development sessions.

## Compliance Panel (GST) — the primary product

A second mode alongside the generic council, for Indian GST notice work.

### THE ONE THING TO UNDERSTAND FIRST: a notice is N defects, not one dispute

A GST notice is a parameter-wise list of defects, and the department raises and
disposes of them **one at a time**. In the matter this product was rebuilt
against — a Tamil Nadu ASMT-10 attachment for a GSTR-9C filer — the
adjudication order says *"Hence this defect is dropped"* eight separate times.
Seven of eight limbs were dropped; the eighth went to a show cause notice.

Everything in the architecture below follows from that. `defects.py` holds the
unit of work; the panel argues only the limbs that turn on law; the export
assembles the reply limb by limb. The first version of this product modelled a
notice as one dispute with one amount and one confidence rating, and every
defect in its output traced back to that single modelling error.

**Why the eighth limb was lost matters more than why seven were won.** The
officer's own findings record it: the taxpayer argued the e-invoicing mandate
date correctly and was understood, but had *"not provided first e-invoice for
the month of august 2023 for verification."* A correct legal position lost a
limb because one system report was not attached. That is why `evidence_gap` is
a first-class output, why `gst_defects.py` names the artefact rather than the
category, and why `evidence_gap_catch` is the number to watch in the evals.

### Architecture

- **`defects.py`** — the defect record, the five postures, triage and validation. Postures are not a severity scale; they are the five different things a reply can say about a limb, each producing different drafting. `explained` / `contested` / `agreed_paid` / `paid_under_protest` / `partial`, with `undecided` as the honest default. Only `contested`, `partial` and `undecided` convene counsel.
- **`notice_tables.py`** — reads head-wise figures off the department's annexure using the checksum the table carries for free: four component amounts that sum to their own printed total. A run that fails its own arithmetic is discarded. **Returns None rather than a guess** — a blank the reviewer can see is safe, a wrong figure they cannot see is not.
- **`domains/gst_defects.py`** — the defect catalogue: heading patterns, provisions engaged, default posture, the evidence list, and the questions an officer puts on that limb at the hearing. **The evidence lists are the product.** Each entry names the artefact an officer asks for before dropping that limb. On the patterns, see "Catalogue patterns are load-bearing" below.
- **`ocr.py`** — optional local OCR for scanned notices, behind `available()`. Cloud OCR is refused on principle: a page image cannot be anonymised before upload, so it would break the draft tier's guarantee. Provenance travels with the text — an OCR-read field carries an `-ocr` source and is shown in the must-confirm state.
- **`calculators.py`** — s.50 interest, the 73/74 penalty stages with their concession deadlines, s.107/112 pre-deposit, appeal limitation, s.128A eligibility. **Python, never a prompt**, for the same reason the reconciliation buckets are: it is arithmetic with a statutory rule attached, and every figure carries its own working so it can be checked line by line. Internal document only — a penalty computation shown to the officer volunteers an admission nobody asked for.
- **`deadlines.py`** — days remaining, urgency bands, worst-first sort, iCalendar export. A missed reply date is the single largest source of avoidable loss in SME practice: it turns a reply into an appeal with a 10% pre-deposit.
- **`pricing.py`** — run cost in rupees, estimated from the firm's OWN completed matters rather than a model price table. A table keyed to model IDs goes stale silently, which is the failure this codebase has already been through once.
- **`domains/gst_authorities.py`** — curated authorities indexed by defect type. See "On case citations" below.
- **`roles.py`** — the four adversarial counsel + chairman. Organised by ROLE IN THE ARGUMENT (Revenue's Advocate / Assessee's Advocate / Procedural / Risk & Ethics), NOT by statute. This is deliberate: a notice concerns one law, so law-specialist panels emit three empty opinions. **These prompts are the product**; everything else is plumbing.
- **`domains/gst.py`** — domain pack. Stable anchors: sections, the full notice-form registry, procedural doctrines, State→High Court map.
- **`panel.py`** — 5 stages: grounding → parallel openings → cross-examination → chairman JSON → citation verification. `merge_determination()` folds the chairman's per-defect answer onto the defects read from the notice; **the notice stays authoritative on heading, numbering and figures**, the chairman only on what we say about them.
- **`verification.py`** — extracts authorities from every defect's list AND from filed text (a citation reaching the reply but not the list is the dangerous one). Each carries its `defect_index`. **Never silently upgrades**: checker failure, unparseable output, or panel-flagged `certainty: to_verify` all resolve to UNVERIFIED.
- **`sanitizer.py`** — draft-tier anonymisation. `IDENTIFIER_RULES` order matters: GSTIN before PAN, or the embedded PAN leaks as a fragment. `audit_leaks()` runs as a pre-flight assertion and the panel ABORTS if anything survives.
- **`users.py` / `auth.py`** — partner/manager/staff with PBKDF2 + session tokens. Legacy `APP_ACCESS_TOKEN` still works and maps to partner. `redact_for_role` strips `analyses`/`cross_exams` for staff.
- **`export.py`** — **two documents, never one.** See below.
- **`reconciliation.py`** — 2A/2B vs 3B workbook ingestion. Parses xlsx/csv, detects columns by alias, classifies each row into a `RECONCILIATION_BUCKETS` entry, aggregates by bucket.

### export.py produces TWO documents and they must never merge

`build_filing_reply()` goes to the proper officer, on the **client's**
letterhead over its authorised signatory, in the A-to-O framework — cause
title, Disputes at a Glance, issue-wise reply, consolidated payments,
evidentiary index, prayer with one relief per defect, signature block.

`build_file_note()` stays in the office and carries everything the other must
not: postures and why, filing blockers, evidence gaps, exposure, unverified
authorities, panel disagreements, board summary. Stamped
**INTERNAL — NOT FOR SUBMISSION** on every page.

This split exists because a single combined pack was produced and read by a
practising partner. Its "Points for Reviewer Attention" section carried *"worst
realistic monetary exposure … approx. Rs. 2.02 lakh"* and its file note
recorded that the firm's confidence was *"defensible, not strong, because … the
team has not yet verified line-by-line"* — in the same file as the text
intended for the department. `TestTheWallBetweenDocuments` asserts every class
of that leak from both sides. Do not merge these builders.

Related: the chairman prompt used to forbid a signature block ("the firm
supplies those"). It should not have to. That single instruction is why every
exported document needed manual surgery before it could be filed.

### On case citations — a documented rule that was reversed

`domains/gst.py` used to carry "never hardcode case citations", on the
reasoning that case law is volatile and mis-citing it is the core professional
risk. The reasoning holds; the conclusion did not. A panel told to generate its
own authorities, with a verifier that downgrades anything doubtful, produced a
reply carrying nine authorities of which eight were bare statutory sections and
one was an off-point case marked *to be confirmed*. A reply with no law is not
the safe outcome, only a worse one.

The rule that replaced it, enforced in `export.py`:

1. The curated library is a starting point, never an output.
2. Every entry is verified against live sources on every run, exactly as a
   model-generated citation is.
3. **An authority that does not come back VERIFIED never reaches the filing
   document.** It goes to the file note with a confirm-before-filing flag.

`_is_filable()` gates this. If verification did not run at all the index is
empty and nothing is filable — the correct failure direction.

### The reconciliation rows never reach a model
A real 2A/3B reconciliation is thousands of invoice lines — roughly 500k tokens, and third-party supplier data the client has no business disclosing. Bucketing is deterministic arithmetic, so it happens in Python. Only `reconciliation_brief()` (a ~200–700 token aggregate: bucket, count, amount, share, legal position) is put in front of the panel. Do not "improve" this by passing rows to a model. `tests/test_reconciliation.py::TestBriefing` asserts both halves: no invoice-level data travels, and briefing size is independent of row count.

Each bucket carries its own legal position and strength — `strong` (RCM/import IGST/ISD, excluded at the threshold; timing), `defensible` (amendment, supplier error, clerical), `weak` (non-filer — the s.16(2)(c) exposure), `concede` (ineligible). `UNRECONCILED` is named so it cannot be read as benign. Supplier GSTINs are masked on the anonymising tier.

### Stage 2 is cross-examination, NOT ranking
The generic council ranks because every model answers the same question. Panel counsel answer *different* questions, so ranking is meaningless. Do not reintroduce it here.

### Triage: most limbs do not need a panel
On the reference eight-defect notice, six limbs are answered by reconciliation,
documents or a payment and two turn on law. Convening four counsel on all eight
produces prose where a table was wanted and pays four models to write it.
`defects.triage()` splits them; the role prompts tell counsel where their effort
belongs. **Conceding a limb is a positive recommendation**, not a failure — the
prompts say so explicitly, because on the reference matter three limbs were
correctly conceded and paid, and that is what made the contested limbs credible.

### Two tiers = risk tiers
`draft` forces anonymisation and watermarks every exported page; `pro` sends
full facts with ZDR routing (`provider: {"data_collection": "deny"}`).
Identifiers are restored locally after the run so the partner reads real names
the model never saw.

There was a `free` tier on OpenRouter's `:free` endpoints. Every ID in it went
stale and the tier failed silently in production — **including notice reading**,
because `intake.extract_fields_assisted` borrows the tier's grounding model.
One root cause, two symptoms that looked unrelated. `TIER_ALIASES` maps stored
`tier="free"` matters to `draft`, never falling through to `pro`, which would
send real identifiers on a re-run of work the user chose to anonymise.

### Adding the Income Tax pack
New file in `domains/` with the same interface (including `DEFECT_TYPES` and
the authorities helpers), registered in `domains/__init__.py`. No change to
`panel.py`, `roles.py`, `verification.py`, `export.py` or the UI.

### Catalogue patterns are load-bearing, and they fail in both directions

A limb that does not segment is never answered, and an unanswered limb is
confirmed unopposed. A pattern that matches too much invents a limb and hands
it a neighbour's figures. Both have happened, and the golden set exists mainly
to catch them:

- `e[\s-]?invoic` with no leading `\b` matched the ordinary phrase **"the
  invoice"**, so nearly every notice grew a phantom e-invoicing limb.
- A bare `refund` matched the s.73 boilerplate *"tax not paid or short paid or
  erroneously refunded"*, so every s.73 demand grew a refund limb.
- A bare `interest under section 50` matched the demand boilerplate carried by
  almost every notice. **Do not add it back.**
- Conversely, `excess ITC availed` required those words adjacent, so the
  department's own standard wording — *"Input tax credit availed in excess of
  that appearing in GSTR-2B"*, the most common defect in Indian GST practice —
  matched nothing at all.

Rule of thumb: a pattern must match **heading language**, not statutory prose
that appears in every notice. Add one, then run
`uv run pytest tests/test_golden_set.py`.

Heading detection has three signals in priority order — the department's own
`Defect -N` numbering, bulleted parameter headings, then plain numbered
headings (`1.`, `2.`) where the heading text ALSO matches the catalogue. The
last resort is a loose catalogue scan that can only ever produce **one limb per
defect type**, which is why the numbered signal matters: an RFD-08 objecting to
a refund on two grounds came back as one limb with both figures.

### Gotchas
1. `_extract_json` handles fenced/prose-wrapped chairman output; failure produces `_fallback_determination` with a "must not be filed" risk flag — never a silent empty result.
2. Matters live in `data/matters/`, conversations in `data/conversations/`. Both atomic-write.
3. Model IDs churn on OpenRouter. Startup validation reports stale IDs — check `/api/health` and the Admin > Panel configuration tab first when a tier silently fails.
4. The sanitizer leak test is sacred. A failure there is a confidentiality breach, not a bug.
5. **Departmental PDFs do not emit in reading order.** The first limb's table is extracted ABOVE its own bullet heading, which is why `segment()` gives the FIRST defect a `preamble` and only the first — so no later limb can be handed a figure belonging to its neighbour.
6. **Bound the last defect.** Without `ANNEXURE_BOUNDARY_RE` the final limb absorbs every annexure in the document; a Rs. 44 interest limb once read Rs. 1.24 crore.
7. Extraction that cannot read a figure must report it unread. `amount_unread` surfaces in the UI as an empty field to fill. Never fill it with a zero.

### Frontend
Design tokens in `theme.css` (light/dark via `data-theme` on `<html>`); components never hardcode colours. `format.js` holds helpers/constants separately from `shared.jsx` so React Fast Refresh works — `POSTURES` and friends live there for the same reason. Views: Dashboard, PanelWorkspace (multi-file intake + defect review + live deliberation), DefectList, MatterList, MatterDetail (two separate downloads), AdminPanel, GeneralCouncil.

### Evals — two harnesses, and the free one runs on every push

`evals/golden/` holds nine committed cases across ASMT-10, DRC-01 (s.73 and
s.74), DRC-01B, DRC-01C, ADT-02, RFD-08, REG-17 and MOV-07. Every case is
**synthetic** and carries a provenance note; a test enforces both, because
these ship in a public repository and a golden case built from a client matter
must never be committed. `gst-asmt10-multilimb-fy2324` mirrors the reference
matter: eight limbs, and an e-invoicing limb that is lost on a missing IRP
acknowledgement despite a correct legal position.

**`tests/test_golden_set.py` — free, runs on every push.** Segmentation and
figure reading are decided in Python, so they are scored without a single model
call: every limb must be found, every head-wise amount must match the annexure,
and the limbs must reconcile to the notice's own printed total. This is where
six silent extraction bugs were caught, none of which the paid harness would
have found, because nobody runs the paid harness on every change.

**`evals/run.py` — costs money, run before shipping a prompt change.** The two
numbers that matter are `defect_coverage` (a limb the panel never finds cannot
be answered, and an unanswered limb is confirmed unopposed) and
`evidence_gap_catch` (scored against a limb that was argued correctly and lost
anyway). No prompt change should ship without running these.

---

## Project Overview

LLM Council is a 3-stage deliberation system where multiple LLMs collaboratively answer user questions. The key innovation is anonymized peer review in Stage 2 — models never see model names, and never see or rank their own response (self-vote exclusion). The app supports multi-turn conversations, quick vs full deliberation modes, web-search grounding, cost accounting, and private cloud deployment behind a bearer token.

## Architecture

### Backend Structure (`backend/`)

**`config.py`**
- Every setting is env-overridable (loaded via `.env`); see `.env.example` for the full list
- `COUNCIL_MODELS` (comma-separated env or default list), `CHAIRMAN_MODEL`, `TITLE_MODEL`
- `REASONING_EFFORT` (low/medium/high/none), `REQUEST_TIMEOUT`, `MAX_RETRIES`, `HISTORY_MAX_TURNS`
- `APP_ACCESS_TOKEN`: shared secret; empty = auth disabled (local dev only)
- Backend runs on **port 8001** (NOT 8000 - user had another app on 8000)

**`openrouter.py`**
- `query_model()`: single async model query. Returns `{'ok': True, 'content', 'reasoning_details', 'usage'}` or `{'ok': False, 'error'}` — never None
- Retries transient failures (network errors, 408/409/429/5xx) with exponential backoff (2s, 4s); non-retryable statuses fail fast
- If a model rejects the `reasoning` parameter with HTTP 400, the parameter is stripped and the call retried without consuming retry budget
- Requests `usage: {include: true}` so OpenRouter returns token counts and dollar cost
- `web_search=True` adds the OpenRouter web plugin (`plugins: [{"id": "web"}]`)
- Treats 200-with-error-body and empty-content responses as failures

**`council.py`** - The Core Logic
- `build_history_messages()`: converts stored conversation messages into chat history (user turns + prior Stage 3 answers), capped at `HISTORY_MAX_TURNS` exchanges. Passed to Stage 1 and Stage 3 as real message turns; Stage 2 gets a truncated text snippet via `format_history_snippet()`
- `stage1_collect_responses()`: parallel queries; returns `(results, failures)` — failures carry per-model error strings surfaced in the UI
- `stage2_collect_rankings()`:
  - Global labels "Response A/B/C..." assigned by Stage 1 order; `label_to_model` mapping for de-anonymization
  - **Each ranker gets a custom prompt excluding its own response** — different rankers see different subsets, so per-ranker `valid_labels` are tracked
  - Rankers with fewer than 2 responses to rank are skipped
  - Returns `(rankings, label_to_model, failures)`; each ranking includes `parsed_ranking`, `own_label`, `parse_complete`
- `stage3_synthesize_final()`: chairman receives responses, reviews, **the label→model mapping, and the aggregate ranking** so it can connect peer verdicts to specific answers; prompt instructs it to resolve disagreements explicitly rather than averaging
- `parse_ranking_from_text(text, valid_labels)`: extracts the LAST "FINAL RANKING:" section, prefers the numbered-list format, deduplicates labels (first occurrence wins), and drops labels not in `valid_labels`
- `calculate_aggregate_rankings()`: positions are **normalized to [0,1] within each review** (rankers rank different subset sizes due to self-exclusion), then averaged; output sorted by `score` ascending (lower = better) and includes raw `average_rank` + `rankings_count`
- `run_council_stream()`: async generator yielding stage events; single source of truth for orchestration. `run_full_council()` consumes it for the non-streaming endpoint. Modes: `"full"` (3 stages) and `"quick"` (skips Stage 2)
- `_sum_usage()`: aggregates tokens/cost across all stages into `metadata.usage`

**`auth.py`**
- `require_auth` dependency: constant-time comparison of `Authorization: Bearer <token>` against `APP_ACCESS_TOKEN`; no-op when unset

**`storage.py`**
- JSON-based conversation storage in `data/conversations/` (env-overridable `DATA_DIR` — read dynamically via `config.DATA_DIR` so tests can monkeypatch it)
- **Atomic writes** (tempfile + `os.replace`) — a crash can't corrupt conversation files
- Corrupt files are skipped in listings and return None on read, never crash the app
- Assistant messages persist `{role, stage1, stage2, stage3, metadata}` — metadata (mapping, aggregates, failures, usage) IS persisted now, so reloaded conversations render fully
- `delete_conversation()` supported

**`main.py`**
- All `/api` routes on an APIRouter behind `require_auth`; `/healthz` is unauthenticated (hosting platform health checks)
- `POST /api/conversations/{id}/message/stream` (SSE) is the primary path; events: `stage1_start/complete`, `stage2_start/complete`, `stage3_start/complete`, `summary` (authoritative metadata incl. usage), `title_complete`, `complete`, `error`. `stage1_complete`/`stage2_complete` also carry `failures`
- `SendMessageRequest`: `content`, `mode` ("full"/"quick"), `web_search` (bool)
- Startup hook validates configured model IDs against OpenRouter's catalog (best-effort, non-fatal); results in `GET /api/health`
- Serves `frontend/dist` as static files when present (single-container deployment); mounted after API routes so `/api` wins

### Frontend Structure (`frontend/src/`)

**`api.js`**
- Relative URLs only (`/api/...`): Vite dev server proxies to :8001 (see `vite.config.js`); production is same-origin
- Bearer token stored in localStorage (`llm_council_token`); `ApiError` carries `.status` so the app can detect 401 and show the login screen
- SSE parsing buffers across chunks (events can span reads)

**`App.jsx`**
- Auth gate: `checkAuth` on mount → login screen on 401; any later 401 clears the token and re-gates
- `updateLastMessage` helper immutably updates the in-flight assistant message per SSE event
- Stream errors mark the message with an inline error instead of deleting the exchange
- Conversation delete with confirm dialog

**`components/ChatInterface.jsx`**
- **Input is always visible** — multi-turn conversations are supported (the original app hid the input after one exchange)
- Per-message options: Full council / Quick select, Web search checkbox
- `FailureNotice` shows per-model failures; `UsageLine` shows cost/tokens/mode
- Enter to send, Shift+Enter for new line

**`components/Stage2.jsx`**
- Tab view of RAW evaluation text; de-anonymization happens CLIENT-SIDE for display
- "Extracted Ranking" shown below each evaluation so users can validate parsing
- Aggregate rankings display normalized `score` (0=best, 1=worst) with review counts

**`components/Stage3.jsx`** — final synthesized answer, green-tinted (#f0fff0)

**Styling** — light mode, primary #4a90e2; all ReactMarkdown wrapped in `.markdown-content` (defined in `index.css`)

## Key Design Decisions

### Self-Vote Exclusion (Stage 2)
Models reliably recognize their own writing style, so letting them rank their own response biased the aggregate. Each ranker now sees only its peers' responses. Consequence: rankers rank different subset sizes (a stage-1 failure means that model still ranks ALL responses since none is its own), so aggregate scores use within-review normalization, not raw average positions.

### Stage 2 Prompt Format
Strict "FINAL RANKING:" numbered-list format for parseability. The parser prefers the numbered format, falls back to bare "Response X" mentions, dedupes, and validates against the labels that ranker actually saw.

### Chairman Context
The chairman previously couldn't connect "Response A is best" to any model. It now receives the mapping and the computed consensus, with explicit instructions to exercise judgment (not blindly follow rank 1) and to resolve disagreements explicitly.

### Error Handling Philosophy
- Continue with successful responses if some models fail (graceful degradation), but **surface every failure to the user** (per-model error notices in the UI)
- Retry transient failures before giving up; never fail the whole request for one model
- Chairman failure returns an explicit error message but Stage 1/2 results remain viewable

### Cost Transparency
Every model call requests usage accounting; totals are aggregated per exchange and persisted, so the user always knows what a deliberation cost.

## Common Gotchas

1. **Module Import Errors**: Always run backend as `python -m backend.main` from project root; backend modules use relative imports
2. **Ranking Parse Failures**: `parse_complete: false` on a stage2 result means the ranker didn't rank everything it saw — the parser keeps whatever was valid
3. **Different label sets per ranker**: don't assume every ranker ranked every label; that's why aggregate uses normalized scores
4. **Auth in dev**: unset `APP_ACCESS_TOKEN` disables auth entirely — never deploy that way
5. **`config.DATA_DIR` is read at call time** in storage.py (via `config.DATA_DIR`), not import time — keep it that way for testability
6. **SSE events can span TCP chunks** — the frontend buffers; don't regress to per-chunk parsing

## Testing

```bash
uv run pytest
```

`tests/test_council.py`: parser edge cases (duplicates, invalid labels, repeated headers, fallbacks), aggregate normalization, history building/truncation.
`tests/test_storage.py`: atomic writes, corrupt-file resilience, metadata persistence, deletion.

Startup logs and `GET /api/health` report model IDs missing from OpenRouter's catalog — check there first when a model silently fails.

## Deployment

- **Docker**: multi-stage build (Node → Python via uv); container serves API + built frontend on :8001; conversation data at `/app/data` (mount a volume)
- **Render**: `render.yaml` blueprint — Docker runtime, persistent disk at `/app/data`, `OPENROUTER_API_KEY` set manually, `APP_ACCESS_TOKEN` auto-generated
- `/healthz` is the unauthenticated health check endpoint

## Data Flow Summary

```
User Query (+ conversation history, mode, web_search)
    ↓
Stage 1: Parallel queries (history-aware, optional web search) → [responses + failures]
    ↓ (mode=full and ≥2 responses)
Stage 2: Anonymize, exclude self → parallel ranking queries → [evaluations + parsed rankings]
    ↓
Aggregate (normalized positions) → [sorted by score]
    ↓
Stage 3: Chairman synthesis (history + responses + reviews + mapping + consensus)
    ↓
summary event: {stage1, stage2, stage3, metadata: {mapping, aggregates, failures, usage, mode}}
    ↓
Persisted to storage (metadata included) + streamed to frontend via SSE
```

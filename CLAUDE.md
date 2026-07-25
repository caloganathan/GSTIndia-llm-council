# CLAUDE.md - Technical Notes for LLM Council

This file contains technical details, architectural decisions, and important implementation notes for future development sessions.

## Compliance Panel (GST) — the primary product

A second mode alongside the generic council, for Indian GST notice work.

### Architecture

- **`roles.py`** — the four adversarial counsel + chairman. Organised by ROLE IN THE ARGUMENT (Revenue's Advocate / Assessee's Advocate / Procedural / Risk & Ethics), NOT by statute. This is deliberate: a notice concerns one law, so law-specialist panels emit three empty opinions. **These prompts are the product**; everything else is plumbing.
- **`domains/gst.py`** — domain pack. Hardcodes only STABLE anchors (sections, notice-form codes, procedural doctrines, State→High Court map). **Never hardcode case citations** — they are volatile and mis-citing them is the core professional risk. Case law is generated then verified.
- **`panel.py`** — 4 stages: parallel openings → cross-examination → chairman JSON → citation verification. Mirrors `run_council_stream`'s event shape.
- **`verification.py`** — extracts authorities from the chairman's table AND the draft body (a citation reaching the reply but not the table is the dangerous one). **Never silently upgrades**: checker failure, unparseable output, or panel-flagged `certainty: to_verify` all resolve to UNVERIFIED.
- **`sanitizer.py`** — free-tier anonymisation. `IDENTIFIER_RULES` order matters: GSTIN before PAN, or the embedded PAN leaks as a fragment. `audit_leaks()` runs as a pre-flight assertion and the panel ABORTS if anything survives.
- **`users.py` / `auth.py`** — partner/manager/staff with PBKDF2 + session tokens. Legacy `APP_ACCESS_TOKEN` still works and maps to partner. `redact_for_role` strips `analyses`/`cross_exams` for staff.
- **`export.py`** — DOCX reply pack. The ICAI review disclaimer is mandatory and not configurable away by the UI.

### Stage 2 is cross-examination, NOT ranking
The generic council ranks because every model answers the same question. Panel counsel answer *different* questions, so ranking is meaningless. Do not reintroduce it here.

### Two tiers = risk tiers
`free` forces anonymisation and blocks export; `pro` sends full facts with ZDR routing (`provider: {"data_collection": "deny"}`). Identifiers are restored locally after the run so the partner reads real names the model never saw.

### Adding the Income Tax pack
New file in `domains/` with the same interface, registered in `domains/__init__.py`. No change to `panel.py`, `roles.py`, `verification.py` or the UI.

### Gotchas
1. `_extract_json` handles fenced/prose-wrapped chairman output; failure produces `_fallback_determination` with a "must not be filed" risk flag — never a silent empty result.
2. Matters live in `data/matters/`, conversations in `data/conversations/`. Both atomic-write.
3. Free model IDs churn on OpenRouter. Startup validation reports stale IDs — check `/api/health` and the Admin > Panel configuration tab first when a tier silently fails.
4. The sanitizer leak test is sacred. A failure there is a confidentiality breach, not a bug.

### Frontend
Design tokens in `theme.css` (light/dark via `data-theme` on `<html>`); components never hardcode colours. `format.js` holds helpers/constants separately from `shared.jsx` so React Fast Refresh works. Views: Dashboard, PanelWorkspace (intake + live deliberation), MatterList, MatterDetail, AdminPanel, GeneralCouncil.

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

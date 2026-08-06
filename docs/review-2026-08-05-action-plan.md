# Independent review — 5 August 2026 — findings and action plan

Reviewed as a senior GST practitioner would review a tool before letting the
firm's name near its output: the statutory modules line by line, the drafting
and export path, the confidentiality machinery, the frontend workflow, the
evals, and every document in the repository. Baseline: branch
`claude/gst-accounting-ai-review-7iqaq2`, test suite green
(789 passed, 5 skipped).

**Verdict in one paragraph.** The architecture is right and unusually honest:
defect-wise modelling, the two-document wall, statutory arithmetic in Python,
fail-closed citation verification, a synthetic golden set with a provenance
lock. Most of what this review found is the distance between those stated
guarantees and the code that is supposed to enforce them. Three of the gaps
are serious enough that the product should not run a live client matter until
they are closed (P0 below), and the curated authorities library contains one
entry that is wrong in both forum and proposition — the exact failure the
product exists to prevent. Everything is fixable, none of it requires
re-architecture, and the fix list below is ordered so a dev agent can work
top to bottom.

Conventions: **[P0]** confidentiality or filing integrity — close before any
real matter. **[P1]** professional correctness — close before offering the
output to a partner as reliable. **[P2]** product quality. **[P3]** docs and
hygiene. Each item names the files; line numbers are as of this branch.

---

## STATUS — 6 August 2026: everything below is closed except one item

| PR | Package | Merged |
|---|---|---|
| #19 | P0.1–P0.4 — the wall and the scrub | yes |
| #20 | P0.5–P0.8 — tier and transport safety | yes |
| #21 | P1.8–P1.11 — CI and eval-harness honesty | yes |
| #22 | P1.1–P1.4 — statute pack | yes |
| #23 | P1.7 + half of P1.6 — auth hardening | yes |
| #24 | P1.5, P2 — frontend correctness | yes |
| #25 | P2 — workflow gaps and accessibility | yes |
| #26 | P3 — documentation | yes |

Suite: 789 → **916 passing**. CI (`.github/workflows/test.yml`) now runs it on
every push and pull request, which it did not when this review was written.

**The one item still open: P1.6, the default model IDs.** The sandbox this
work was done in denies `openrouter.ai` by network policy, so the slugs could
not be checked against the live catalogue — and guessing at them is the exact
failure the item exists to fix. On the current defaults a fresh install fails
on **both** tiers. Anyone with catalogue access should pin them and add the
test. The validation half shipped in #23: startup now checks each tier's
`grounding` model, whose omission caused the original silent notice-reading
outage.

Two findings turned out to be **worse** than this document recorded, and the
fixes went further than what is written below:

- *Orissa Concrete & Allied Industries* was not merely an incomplete citation.
  It is a **1998 Calcutta High Court excise matter**, not an Orissa ruling on
  s.17(5)(d) at all — the genuine Orissa authority on that point is Safari
  Retreats, already held. It was removed rather than verified.
- Session tokens were stored **in clear** as the dict key in `users.json`, and
  survived a password change. That is a live credential the moment the store
  is readable, needing no password and tripping no lockout. Not in the
  original P1.7 list; fixed in #23.

---

## P0 — Confidentiality and filing integrity

### P0.1 The draft tier's anonymisation does not cover defect text, and the abort gate cannot see the leak
`backend/sanitizer.py:49-50` scrubs only `issues`, `facts`,
`documents_available` and drops `client_name`/`gstin`/`client_ref`. It never
touches `matter["defects"]` — but `backend/roles.py:349` sends
`defect["department_contention"][:600]` (raw notice prose, which routinely
carries the GSTIN and the taxpayer's name) and `defect["heading"]` to every
counsel. The pre-flight `leak_probe` at `backend/panel.py:243-247` is built
from the same three scrubbed fields, so `audit_leaks()` structurally cannot
catch it, and on the draft tier `zdr=False`, so the text goes to retaining
endpoints.
**Fix:** scrub `defects[*].heading`, `department_contention`,
`notice_extract` and any free text inside defects in `sanitize_matter()`;
build the leak probe from the fully rendered `format_matter()` output, not a
hand-listed field subset. Add a test that plants a GSTIN inside a defect
heading and asserts the run aborts.

### P0.2 Unverified authorities still reach the filing document via `legal_framework`
`backend/export.py:571-579` prints every `defects[*].legal_framework` entry
into the filing reply with no `_is_filable()` gate — unlike `authorities`
immediately below (`export.py:584-587`). The chairman prompt
(`roles.py:588`) invites circulars/notifications into that field, and
`verification.py:113-116` checks them — but the export ignores the result.
**Fix:** filter `legal_framework` through `_is_filable(entry["provision"],
verified)` exactly as `authorities` is filtered; unverified entries go to the
file note with the confirm-before-filing flag. Extend
`tests/test_export.py` to cover it.

### P0.3 Citations inside filed prose are detected, flagged — and filed anyway
`verification.py:118-121` extracts citations from `submission`, `facts`,
`our_position`, `preliminary_submissions` (source `filed_text`), precisely
because "a citation reaching the reply but not the list is the dangerous
one". But `export.py:392-394, 567-569, 604-619` print those strings verbatim.
A NOT_FOUND case named inside a SUBMISSION paragraph is listed in the file
note and still goes to the officer.
**Fix:** any `filed_text` authority not returning VERIFIED must either be
redacted from the prose or added to `filing_blockers` so the filing export is
blocked until resolved. Test both directions.

### P0.4 Staff receive the unredacted deliberation over SSE
`GET /api/matters/{id}` applies `redact_for_role` (`main.py:333`), but
`POST /api/panel/run` (`main.py:566-596`) streams `stage1_complete` /
`stage2_complete` / `summary` verbatim to any authenticated user; the only
gate is client-side (`frontend/src/components/Deliberation.jsx:148`), which
also fails open (`!== false` instead of `=== true`).
**Fix:** pass each SSE payload through `redact_for_role` server-side before
yielding; change the frontend check to require the positive grant. Add a test
that a staff session's stream carries no `analyses`/`cross_exams`.

### P0.5 Unknown tier strings fall through to `pro`; a typo in `DEFAULT_PANEL_TIER` 500s every run
`backend/config.py:318-321`: `TIERS.get(key or DEFAULT_TIER,
TIERS[DEFAULT_TIER])`. `TIER_ALIASES` is exact-match/case-sensitive, so
`"Free"`, `" free"` or any typo lands on the default — which is `pro`, the
non-anonymising tier, from unvalidated user input on `/panel/run`,
`/panel/extract`, `/panel/reconciliation`. Separately, the eager
`TIERS[DEFAULT_TIER]` raises `KeyError` for *every* tier when
`DEFAULT_PANEL_TIER` is misspelled.
**Fix:** normalise (`strip().lower()`), route through `TIER_ALIASES`, reject
unknown keys with a 400 at the API layer, make the internal fallback `draft`
(never `pro`), and validate `DEFAULT_TIER` at import. Add direct tests:
`get_tier("free")["anonymise"] is True`, `get_tier("FREE ")` same,
`get_tier("typo")` never returns pro.

### P0.6 Intake anonymisation discards the replacement map — placeholders are never restored
`backend/intake.py:958` calls `sanitizer.scrub_text(text, {}, ...)` with a
throwaway dict, so the model's `issues`/`facts` come back containing
`[GSTIN-1]` / `the Taxpayer`, are stored on the matter
(`intake.py:1130-1132`) and print into both exported documents. This
contradicts the restore-locally guarantee.
**Fix:** keep the replacements dict and apply `restore_structure` to the
assisted fields before they enter `fields`. Test with a GSTIN-bearing notice
text.

### P0.7 ZDR routing is missing on two of five stages
`backend/grounding.py:111-118` and `backend/verification.py:260-268` call
`query_model` without `zdr=`, defaulting to `False`. Grounding carries client
facts; the verifier carries every authority and proposition.
**Fix:** thread `zdr` from `panel.py` into both, as stages 1–3 already do.

### P0.8 Matter IDs are joined into filesystem paths unvalidated
`backend/storage.py:222-235` and `125-138` interpolate caller-supplied IDs
into `os.path.join(...)`. `../users` targets the user store — which holds
PBKDF2 hashes and **live session tokens** (`users.py:245-249`). Today only
Starlette's route regex accidentally protects it.
**Fix:** validate IDs against `^[A-Za-z0-9_-]{1,64}$` inside `storage.py`
before any path construction, and test traversal attempts.

---

## P1 — Professional correctness (statute and authorities)

### P1.1 Authorities library: one entry wrong in substance, one unverifiable, one missing a critical caution
`backend/domains/gst_authorities.py`:
- **Gobinda Construction** (line ~210) is cited as Orissa HC for "s.16(4) is
  procedural, not substantive". The reported Gobinda Construction ruling is
  **Patna High Court**, and it **upheld** s.16(4) against the taxpayer. As
  drafted this entry supports the opposite of what the case held — the exact
  "authority that does not say what it is said to say" failure. **Remove it.**
  The correct primary answer to a legacy time-bar limb is already in the
  library (ss.16(5)/16(6)); if a judicial entry is wanted, curate one that a
  partner has actually verified.
- **Safari Retreats** (line ~84) carries no caution about the **Finance Act
  2025 retrospective substitution in s.17(5)(d) ("plant or machinery" →
  "plant and machinery", w.e.f. 01.07.2017)** enacted to neutralise the
  ruling. Citing it unqualified in 2026 is professionally risky. **Add a
  note** stating the amendment, that the functional-test reasoning survives
  only in narrowed form, and that current status must be confirmed on every
  use; make sure the verification layer treats it as at-risk rather than
  waving through a famous name.
- **"Orissa Concrete & Allied Industries v. Commissioner, 2023 SCC OnLine
  Ori"** (line ~125) is an incomplete citation (no number). Verify against a
  reporter or drop it.

### P1.2 Section 74A is silently treated as Section 74
`backend/calculators.py:240` (`section.startswith("74")`) routes a
Section 74A notice (FY 2024-25 onwards — these are arriving now) to the s.74
penalty stages: 15%/25%/100% with 30-day windows, where s.74A has its own
scheme (10% non-fraud / 100% fraud tracks, **60-day** concession windows).
`amnesty_128a` has the same startswith problem (harmless in outcome, wrong in
stated reason). The defect catalogue and `matter_computations` have no 74A
awareness either.
**Fix:** add a `"74A"` entry to `PENALTY_STAGES` with both tracks and 60-day
deadlines, match `74A` before `74`, correct the 128A reason text, and add
tests. The grounding stage should confirm the live 74A position as it does
for everything else.

### P1.3 Appeal limitation uses 90+30 days for "three months + one month"
`backend/calculators.py:372-373`. Section 107(1)/(4) speaks in months;
under the General Clauses Act a "month" is a calendar month, and 90 days ≠ 3
months at the margins (e.g. communicated 30 May → 30 August is 92 days). The
current code can mark an in-time appeal `condonable` or a condonable one
`time_barred` — exactly the class of advice a firm gets sued over.
**Fix:** compute calendar-month arithmetic (same-day-of-month with
end-of-month clamping), keep the day counts for display, and add boundary
tests either side of a month-end. Consider a parallel `112` limitation
function now that GSTAT is operational (the module computes the s.112
pre-deposit but not its limitation).

### P1.4 Unread amounts print as ₹0; `amount_note` is rendered nowhere
`backend/export.py:835` and `:1104` print `Rs. 0`/`Rs. 0.00` for limbs
carrying `amount_unread`; `intake.py:1139` folds unread limbs into
`amount_disputed` as zero, which prints as "Amount in dispute" in the filing
document; and the chairman's `amount_note` field — explicitly required by the
prompt — appears in no export path. Violates the "never fill a blank with a
zero" rule end to end.
**Fix:** render "Not read from the notice — take from the annexure" plus
`amount_note` wherever `amount_unread` is set; mark the matter total
incomplete when any limb is unread. Add the missing direct tests (none of
`test_intake.py`/`test_defects.py` asserts the amount_unread invariant
today).

### P1.5 Frontend can convert an unread amount into a zero, and nothing blocks the run
`frontend/src/components/DefectList.jsx:36-41`: clearing a head input writes
`0` and unconditionally sets `amount_unread: false` — the warning disappears
and the zero reaches export. `PanelWorkspace.jsx:77`: `canRun` ignores
`amount_unread` entirely.
**Fix:** delete the key on empty input, recompute `amount_unread` from "no
head carries a value", auto-expand unread rows, and include "no unread
amounts" in `canRun` with an explanation next to the button.

### P1.6 Default model IDs and the validation blind spot
Every default panel model in `backend/config.py:26-37, 130-152` fails to
match a real OpenRouter slug, so a fresh install fails on both tiers — the
documented free-tier failure mode, reproduced in the defaults. And startup
validation (`main.py:921-924`) omits the tier `grounding` models — the one
model whose staleness caused the original notice-reading outage.
**Fix:** pin defaults verified against `https://openrouter.ai/api/v1/models`,
add the grounding models to the validation set, and add a health-check test.

### P1.7 Auth hardening
- No rate limit, lockout, or failed-attempt counter on `/api/auth/login`
  (`main.py:183-189`), with a predictable bootstrap email
  (`users.py:292`). Add per-email/per-IP backoff persisted with sessions.
- PBKDF2 at 240k rounds (`users.py:55`) is below current guidance and
  `verify_password` accepts any embedded round count with no floor. Raise to
  600k, enforce a floor, rehash on login.
- Session tokens stored raw (`users.py:245`) and survive a password change.
  Store `sha256(token)`; drop a user's sessions on password change.
- `/api/matters/{id}/computations` (`main.py:538-553`) returns
  internal-only exposure material to staff — gate on `view_deliberation`.
- `/readyz` (`main.py:132-148`) discloses filesystem paths and auth posture
  unauthenticated — return status only.

### P1.8 The eval scorers can report false comfort
- `evals/scoring.py:158-170,185-187`: a determination matching no markers
  returns `"mixed"`, which always counts as agreement → 100% on
  `position_agreement` for unscorable text. Return `None` when both counts
  are zero.
- `evals/scoring.py:300-304`: `score_evidence_gaps` matches by index only
  while `score_defects` has a heading fallback — `evidence_gap_catch`, the
  headline number, false-zeroes when the chairman renumbers. Share the
  index-or-heading lookup.
- `evals/scoring.py:99-102`: citation integrity passes when verification
  never ran (`total == 0`) — the opposite failure direction from
  `_is_filable()`. Return unscorable.
- `tests/test_golden_set.py:214-215`: the whole-notice checksum test
  **skips** when any limb is unread, so an extraction regression silently
  removes the guard. Assert reconciliation over the limbs that were read
  plus an explicit expected-unread count per case.
- Add `heading_contains` to every `expected_defects` entry in
  `evals/golden/*.json` (all 21 are `null` today) and assert its presence in
  the well-formedness test.

### P1.9 There is no CI, and three documents claim there is
No `.github/` in the repo, while `CLAUDE.md` and `evals/README.md` say the
golden-set scorer "runs on every push". Add
`.github/workflows/test.yml`: `uv sync --extra ocr && uv run pytest` (the
OCR extra also un-skips the four end-to-end OCR tests that have never run
anywhere but the author's machine).

### P1.10 `.env.example` ships completion ceilings that reproduce a documented failure
`.env.example:65-70` offers `MAX_TOKENS_*` values under a "defaults shown"
banner that are 60–72% **below** the real defaults in
`backend/config.py:229-240` — uncommenting them recreates the
silent-empty-completion failure the config file itself warns about. Update
the five values to the true defaults and copy the warning in.

### P1.11 Missing panel-abort and tier-alias tests
No test exercises `run_panel_stream` aborting on a surviving identifier
(the "sacred" guarantee), and no test asserts
`config.get_tier("free")["anonymise"] is True`. Add both to the suite
(monkeypatch `audit_leaks` → assert error event and zero model calls).

---

## P2 — Product quality

Frontend correctness:
- `PanelWorkspace.jsx:174` — stale `error` closure: an errored run still
  navigates to MatterDetail; a run after any earlier error never navigates.
  Track failure in a local variable inside the SSE callback.
- `MatterDetail.jsx:40-107` — a `status: "draft"` matter renders as
  finished with live export buttons that 400. Branch on status; hide export;
  show "panel did not complete — re-run".
- `MatterDetail.jsx:32-39` / `MatterList.jsx:35` — one failed
  download/delete replaces the whole view. Use dismissible inline alerts.
- `api.js:164-176` — every export saves as `Reply.docx`; parse
  `Content-Disposition` (backend already computes per-matter names).
- `api.js:212-214, 248-250` — streaming calls discard the server's error
  `detail`; reuse the `request()` extraction.
- `Dashboard.jsx:35-36, 122-127` and `main.py:648-652` — SUPERSEDED is
  missing from the verification aggregate and dashboard; surface it as
  loudly as NOT_FOUND.
- `Deliberation.jsx:334-339` — cost shown to staff (strip `usage` from SSE
  metadata for roles without `view_costs`) and shown in USD only (include
  INR via `pricing`).
- `Deliberation.jsx:163-168` — watermark banner copy still references the
  retired free tier and claims draft cannot export. Rewrite.
- `Deliberation.jsx:193-197` — remove the dead single "Export reply pack"
  button (contradicts the two-document rule).
- `PanelWorkspace.jsx:196-205` — add a failed state to the stage track;
  `PanelWorkspace.jsx:89` — a second upload overwrites reviewed fields;
  merge only into unedited fields or warn.
- `PanelWorkspace.jsx:114-180` — 2–4 minute run has no leave-guard and no
  server-side persistence of completed stages; add `beforeunload` and
  persist stage results as they arrive.

Workflow gaps a CA firm will hit in week one:
- No way to add a defect by hand when segmentation finds nothing
  (`DefectList.jsx:29` returns null) — the intake message even instructs the
  user to do so. Add an "Add defect" button.
- `from_scan` defects get no must-confirm treatment in the UI (the flag is
  set in `intake.py:1112` and referenced nowhere in `frontend/src`). Badge
  the rows and amounts; require an explicit confirm before running.
- `format.js:33-34` — abbreviated ₹ (L/Cr) on the defect-review screen
  defeats checking figures against the annexure. Exact `en-IN` grouping in
  review/tables; abbreviations only on dashboard tiles.
- No Status column in `MatterList`/`Dashboard`; a crashed run is
  indistinguishable from a completed one.
- Export buttons vanish for staff with no explanation — show disabled with
  a reason.
- GSTIN gets no 15-char/pattern check; no `due_date >= notice_date` check.
- Reconciliation upload is buried at the bottom of the particulars card —
  promote it to its own card.
- Login: validate the token before persisting it; distinguish 401 from
  transport failure; add a cross-tab `storage` listener; rename the
  localStorage key.

Backend polish:
- `defects.py:517` — a single numbered heading suppresses the catalogue
  fallback; require ≥2 ascending candidates per the docstring's own
  reasoning.
- Supplier masking decided at upload-tier not run-tier
  (`main.py:481-488`) — re-mask inside `sanitize_matter` when the run tier
  anonymises.
- `pricing.py:132,155` — hardcodes the free→draft alias; call
  `config.get_tier`.
- `sanitizer.audit_leaks` never checks the client name — accept and check
  it.
- `notice_tables.py:205-206` — sub-₹10 rows are discarded rather than
  flagged.
- Dead code: `intake.py:262` `DUE_DATE_HINT_RE`, `export.py:50` `WD_SECTION`
  import, `export.py:1133` `build_reply_pack`, `PanelWorkspace.jsx:341`
  no-op ternary.

Accessibility (one pass, one PR):
- Zero `aria-*` attributes in the app; clickable table rows and the defect
  expander are mouse-only; no `:focus-visible` on buttons/nav; labels not
  associated (`AdminPanel.jsx:126-160,293-305`, `DefectList.jsx:115,130`,
  both file inputs); decorative glyphs announced. Keyboard-activatable rows,
  `aria-expanded`/`aria-pressed`, `role="alert"`/`role="status"` on alerts
  and the stage track, `htmlFor`/`id` pairs, `aria-hidden` on glyphs.
- `index.html:6-7` still titles the app "LLM Council" with the Vite
  favicon.

Domain enhancements (propose, gate each on a new golden case):
- Section 74A defect-catalogue and notice-form awareness (pairs with P1.2).
- GSTAT (s.112) limitation calculator and an APL-05 workflow note.
- Candidate catalogue additions, in observed-frequency order: ISD credit
  mismatch; Rule 86B (1% cash) contravention; s.62 best-judgment (GSTR-3A
  route); DRC-01D/recovery intimations. One golden case each — patterns are
  load-bearing, so no pattern lands without one.
- Reconciliation buckets: consider an IMS-era note (invoice accepted/pending
  in IMS is the new timing evidence for 2B-vs-3B limbs).

---

## P3 — Documentation

README (`README.md`):
- Lines 331-339: orphaned upstream text ("looks like ChatGPT…") sits
  unmarked inside the reply-pack section. Move under a
  `## General Council (heritage mode)` heading, and note it ships
  **off by default** (`ENABLE_GENERAL_COUNCIL=false`).
- Lines 341-351: the Features list is 100% generic council. Retitle
  `### General Council features` and add a Compliance Panel feature list
  above it.
- Lines 385-396: the env-var table is the upstream one; every GST variable
  is missing. Replace with a pointer to `.env.example` plus the six
  variables a deployment must actually set.
- Lines 152-155 contradict lines 93-110 on OCR ("deliberately out of
  scope" vs the install instructions). Delete the stale clause,
  cross-reference the Scanned notices section.
- Line 503: "475 tests" → drop the hardcoded count.
- Line 516: Tech Stack omits `STATE_DIR` (matters/users/sessions).
- `docker-compose.yml:9-10`: add `STATE_DIR=/app/data` explicitly, per the
  README's own stated principle.

Other docs:
- `docs/HANDOVER.md` — the branch it describes was merged and deleted; the
  resume recipe fails; the test count is stale. Retitle as historical or
  rewrite post-merge.
- `docs/product-review-and-dev-plan.md` — P0.1/P0.3–P0.6, P1.2, P1.4 have
  shipped but still read as open backlog; add a delivered-as-of status.
- `docs/upstream-licence-request.md:58-62` — presents the rewrite as an
  unexercised fallback; README says it's done. Align (the licence doc is
  the one a lawyer reads).
- `CLAUDE.md:274-287` — documents `ChatInterface.jsx`/`Stage2.jsx`/
  `Stage3.jsx` and an `index.css`, none of which exist; fold into the real
  `### Frontend` section. Update the two "runs on every push" claims once
  CI exists (P1.9).
- `frontend/README.md` — still the Vite template; replace with real
  dev/build/proxy notes.
- `pyproject.toml:2-5` — still `name = "llm-council"`, upstream
  description, version 0.1.0; rename, describe, add authors/license, bump
  to 0.2.0 and surface the version in `/readyz`.

---

## Suggested sequencing for dev agents

1. **PR 1 — the wall and the scrub (P0.1–P0.4).** Sanitizer coverage +
   rendered-prompt leak probe; `legal_framework` and filed-text gating;
   SSE redaction. Tests for each. Nothing else in this PR.
2. **PR 2 — tier and transport safety (P0.5–P0.8).** get_tier hardening,
   intake restore map, ZDR on grounding/verification, storage ID
   validation.
3. **PR 3 — statute pack (P1.1–P1.4).** Authorities scrub (Gobinda out,
   Safari caution, Orissa Concrete verified-or-dropped), s.74A stages,
   calendar-month limitation, amount_unread rendering. A practitioner
   should re-read the authorities diff before merge.
4. **PR 4 — harness honesty (P1.8–P1.11 + CI).** Scorer fixes, golden-set
   heading_contains, checksum-skip removal, abort/tier tests, GitHub
   Actions, .env.example ceilings.
5. **PR 5 — frontend correctness (P1.5 + P2 bugs).**
6. **PR 6 — workflow & accessibility (P2 gaps + a11y pass).**
7. **PR 7 — docs (P3), last**, so the docs describe the fixed system.

Model IDs (P1.6) can ride in PR 2 or stand alone — it needs a human check
against the live OpenRouter catalogue.

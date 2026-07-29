# Product Review & Development Plan — Compliance Panel (GST)

*Independent product review conducted July 2026, from the standpoint of a senior
tax-practice reviewer asking one question: would this make a dent for SME
practising CA firms in India? The assessment portion is summarised here; the
operative part of this document is the phased instruction list for the
development team.*

---

## 1. Verdict in one paragraph

The engine is genuinely above market grade — defect-wise modelling, the
evidence-gap-first design, the filing-reply/file-note wall, and fail-closed
citation verification are the *correct* professional instincts, and none of the
commercial tools in this space (template-reply generators bolted onto
compliance suites) have them. But the product as it stands will not make a
dent, for three reasons that have nothing to do with drafting quality:
**(a)** the front door rejects the most common real input — scanned,
image-only notices; **(b)** it starts *after* the notice has been found,
while the single loudest pain point in Indian practice is notices missed on
the portal leading to ex-parte orders; and **(c)** it is a self-hosted
developer artefact, and SME CA firms do not self-host. Fix the front door and
the lifecycle, wrap it in a hosted offering, and the moat (adversarial panel +
file note + evidence gaps) is real and defensible.

## 2. What is right and must not be touched

These are load-bearing and already correct. Do not "improve" them.

1. **Defect-wise unit of work** (`defects.py`) — matches how officers dispose
   of notices limb by limb.
2. **Evidence gaps as first-class output** (`gst_defects.py` evidence lists) —
   the artefact-naming lists are the product.
3. **The two-document wall** (`export.py`) — filing reply and internal file
   note must never merge. `TestTheWallBetweenDocuments` stays sacred.
4. **Fail-closed citation gating** (`verification.py`, `_is_filable()`) — an
   unverified authority never reaches the filing document.
5. **Deterministic extraction and reconciliation** — regex/checksum before
   models; `None`/`amount_unread` over guesses; invoice rows never reach a
   model; bucketing in Python.
6. **Sanitizer leak audit abort** — a failure there is a confidentiality
   breach, not a bug.
7. **Triage** — most limbs do not convene the panel; conceding a limb is a
   positive recommendation.

## 3. What is built but not genuinely needed

1. **General Council mode as a product surface.** It is heritage, not product.
   For the CA-firm buyer it dilutes positioning, doubles the UI surface,
   carries its own storage/ranking/test machinery, and adds OpenRouter
   model-churn maintenance for a feature no client engagement uses. Keep the
   deliberation *engine*; put the generic chat UI behind a build flag,
   default off in the compliance build.
2. **Stage-2 ranking machinery** (labels, self-vote exclusion, normalised
   aggregate scores) — used only by the council mode. Goes wherever it goes.
3. **Dual auth paths.** Legacy `APP_ACCESS_TOKEN` mapping to partner plus the
   users/PBKDF2 system is two ways to hold the same door. Consolidate on the
   user system; keep the env token only as a bootstrap/breakglass, and log
   loudly when it is used.
4. **Full four-counsel panel on every contested limb.** Triage already limits
   convening, but within convened limbs there is no cheaper gear. Add a
   single-counsel "quick opinion" option per limb (partner's choice) — four
   frontier models plus cross-examination on a routine ₹40k limb is theatre.

Nothing else qualifies. The compliance core is lean; the fat is the inherited
council.

## 4. Development plan

Phases are ordered by what they unblock. P0 is what makes the planned
real-data testing meaningful; P1 is market fit; P2 is distribution. Within a
phase, items are independent unless noted.

### P0 — before comprehensive real-data testing

**P0.1 — Scanned-notice ingestion (OCR).**
- Reality: a large share of state-authority notices (the exact segment this
  product was rebuilt against) are image-only PDFs — stamped, signed, scanned.
  `intake.py` currently detects them and stops. Principled, but the firm's
  experience is "it doesn't work on my notice."
- Instruction: add a **local** OCR path (Tesseract or RapidOCR with Indic
  script packs; no cloud OCR — the image cannot be anonymised before it
  leaves the machine, so cloud OCR breaks the draft-tier privacy promise).
- Every OCR-derived field and figure must carry a `source: "ocr"` flag and
  surface in the review UI in the same must-confirm state as `amount_unread`.
  The existing rule stands: never let an unconfirmed OCR figure flow into a
  filing document.
- Acceptance: a scanned ASMT-10 with annexure produces segmented defects;
  every OCR-read amount is visibly flagged; the checksum validation in
  `notice_tables.py` runs on OCR output and discards failing tables exactly as
  it does for text-layer output.

**P0.2 — Extraction review UX.**
- Real-data testing will live or die on how fast a reviewer can verify and
  correct extraction. Show the source snippet (page + surrounding text)
  alongside each extracted field and each defect's figures; one click to
  correct; corrections logged on the matter.
- Acceptance: for the reference notice, a reviewer can verify all eight limbs'
  headings and figures against source text without opening the PDF separately.

**P0.3 — Committable golden eval set.**
- `evals/golden/` currently holds only the template. The real reference case
  cannot ship (client confidentiality — correct), which means `defect_coverage`
  and `evidence_gap_catch` cannot be run by CI or by any other developer.
- Instruction: author 8–10 **synthetic but realistic** golden cases across the
  registry: ASMT-10 multi-limb, DRC-01 under s.73, DRC-01 under s.74,
  DRC-01C, DRC-01B, RFD-08, REG-17, MOV-07. Each with the full notice text,
  expected defects, expected postures, and at least one deliberately missing
  artefact to score `evidence_gap_catch`. Commit them. Wire `evals/run.py`
  into CI as a manual/nightly job (it spends API money — not per-push).
- Acceptance: a fresh clone can run the evals and reproduce scores.

**P0.4 — Cost in rupees, before and after.**
- Show an estimated cost range **in INR** before a panel run (per tier, based
  on defect count and convened limbs) and the actual INR cost after, persisted
  per matter and totalled on the dashboard. A partner prices engagements in
  rupees; "$0.87" is noise to them.

**P0.5 — Deadline surfacing.**
- `due_date` is captured and printed but nothing watches it. Add: dashboard
  column with days-remaining, sorted overdue-first; visual states (>7 days /
  ≤7 / ≤3 / overdue); an ICS calendar export per matter. Email reminders can
  wait for P2's hosted context — but the dashboard must never let a due date
  pass silently. Missed portal deadlines are the single largest source of
  avoidable loss (ex-parte orders under s.73(9)) in SME practice.

**P0.6 — Operational health surfaced to the partner.**
- Stale OpenRouter model IDs currently surface in `/api/health` and startup
  logs. A partner will not read either. Show a red banner in the UI when any
  configured model fails validation, naming the tier affected. The free-tier
  postmortem in CLAUDE.md is exactly the failure this prevents recurring.

### P1 — market fit

**P1.1 — Appeal module (the current volume market).**
- The wave right now is s.73/74 orders from the FY 2017-20 scrutiny cycle
  moving to first appeal, and GSTAT (operational since 24 Sep 2025) absorbing
  the backlog. The registry already knows APL-01/APL-05; the product cannot
  yet *produce* an appeal.
- Instruction: adjudication orders are also limb-wise — reuse `segment()` on
  DRC-07/orders to extract confirmed limbs and the officer's findings per
  limb. New export builders: **Statement of Facts** and **Grounds of Appeal**
  (APL-01 structure), ground-wise mirroring the defect-wise architecture, plus
  the same internal file note. Deterministic **pre-deposit calculator**
  (s.107: 10% of disputed tax, statutory caps; s.112: additional pre-deposit
  for GSTAT) and a condonation-of-delay draft when the appeal date is beyond
  three months.
- The two-document wall and `_is_filable()` gating apply unchanged.

**P1.2 — Deterministic calculators.**
- All in Python, never a model: s.50 interest (period-wise rates, from return
  due date to payment date, 50(1) vs 50(3)); penalty matrix (73 vs 74 vs 122,
  with the 73(5)/(8) and 74(5)/(8) concession windows and dates); s.128A /
  SPL-01/02 eligibility check on the matter's periods and section. Surface
  results in the file note and (where the posture pays) in the consolidated
  payments table of the reply.

**P1.3 — Vernacular notices.**
- State authorities issue notices and annexures in Hindi, Tamil, Gujarati,
  Marathi, and bilingual formats. Detect language; OCR with Indic packs
  (P0.1); translation for extraction follows the same tier rules as
  everything else (anonymise first on draft tier); every translated figure
  flagged must-confirm. The reply is drafted in English regardless.

**P1.4 — Personal-hearing brief.**
- s.75(4) hearings are where SME firms are weakest. Extend the defect
  catalogue with `hearing_questions` — the questions an officer actually asks
  per defect type — and add a hearing-brief builder to the file note: per
  limb, our position in two sentences, the artefact to hand over, the question
  to expect. Cheap to build, disproportionate value.

**P1.5 — Firm letterhead and templates.**
- Export currently styles a generic professional document. Firms will judge
  the product on whether the output looks like *their* output. Per-firm
  settings: letterhead block (or docx template upload), signatory registry
  (name, designation, membership number), fonts. Injected at export; template
  content is never sent to a model.

**P1.6 — Matter lifecycle, not matter = notice.**
- A real dispute runs ASMT-10 → ASMT-11 → (ASMT-12 or DRC-01A → DRC-01 →
  DRC-06 → hearing → DRC-07) → APL-01 → GSTAT. Link successive notices/orders
  on one matter with a status machine; carry defects forward so the limb
  dropped at scrutiny and the limb confirmed in the order keep their history.
  This is also what makes the appeal module (P1.1) automatic: the confirmed
  limbs are already on file.

### P2 — distribution (without this, none of the above reaches the market)

**P2.1 — Hosted multi-tenant offering.**
- SME CA firms (2–15 partners) buy SaaS; they do not run Docker. Multi-tenant
  hosting, India-region data residency, per-firm isolation, DPDP Act 2023
  posture document, and a client-consent / engagement-letter clause template
  for AI-assisted drafting (the firm's professional-duty cover). Pricing in
  ₹ per matter or per month.

**P2.2 — Notice discovery.**
- The killer feature, staged honestly: first a guided weekly checklist per
  client GSTIN (including the "Additional Notices and Orders" tab that causes
  the missed-notice epidemic); then, via GSP APIs where feasible, automated
  notice retrieval feeding intake directly. Even the checklist version
  converts, because it addresses the fear that actually sells.

**P2.3 — Authority-library curation workflow.**
- `gst_authorities.py` is a static file. Add `last_verified_on` per entry, an
  admin surface to add/retire entries, and a periodic re-verification job
  using the existing verifier. The per-run verification gate stays; this is
  about keeping the *starting point* from rotting.

### Cleanups (fold into whichever phase touches the file)

- Council mode behind a build flag, default off in the compliance build (§3.1).
- Auth consolidation (§3.3).
- Single-counsel quick-opinion gear per limb (§3.4).

## 5. Sequencing note for real-data testing

For the testing round the P0 items are the prerequisites: without OCR (P0.1) a
large fraction of real notices cannot enter the product at all, and without
the review UX (P0.2) and committed evals (P0.3) the testing produces anecdotes
rather than scores. Recommend running the real-data round against
`defect_coverage` and `evidence_gap_catch` per notice, plus two new counts:
fields corrected by the reviewer per notice, and minutes from upload to
verified extraction.

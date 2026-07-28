# Evaluation harness

How you find out whether the panel is any good — and, more importantly, whether
a change to the prompts made it better or worse.

Without this you are tuning prompts on vibes. With it, every prompt change is
measured against matters where you already know the right answer.

## The idea

A **golden set** is a folder of past matters where you know what actually
happened: the notice, the position your firm took, the procedural points that
mattered, and the outcome if there is one. The harness runs the panel over
them and scores the output on what can be measured automatically, then hands
you a scorecard for the judgement calls only a partner can make.

## What is scored automatically

| Metric | What it tells you | Target |
|---|---|---|
| **Citation integrity** | % of authorities that verified. `NOT_FOUND` means fabricated | 0 not-found, ever |
| **Issue coverage** | Did the panel find the issues the notice actually raised? | ≥ 90% |
| **Procedural catch** | Did Procedural Counsel spot the limitation / jurisdiction point you spotted? | ≥ 80% |
| **Position agreement** | Did the chairman land on the position your firm actually took? | ≥ 70% |
| **Determination integrity** | Did the chairman return usable structured output at all? | 100% |
| **Cost and latency** | What a run costs and how long it takes | your call |

Issue coverage and procedural catch use keyword matching against what you
recorded in the expectations file. That is deliberately crude: it is a
regression signal, not a grade. The grade comes from you.

## What only you can score

The scorecard writes out four questions per matter. These are the ones that
decide whether the product is real:

1. **Would you sign it?** (yes / with minor edits / no) — the only metric that
   ultimately matters.
2. **Did it find anything you missed?** This is where the upside is.
3. **Did it say anything wrong?** Not just unverified — actually wrong.
4. **Time to a filable draft** versus your normal process.

## Setting up a golden set

Create one JSON file per matter in `evals/golden/`. Start with 8-10 — enough
to see a pattern, few enough to build in an evening. Use matters you have
already filed, where you know how it went.

```json
{
  "id": "gst-001",
  "description": "ITC mismatch, notice issued beyond limitation",
  "intake": {
    "client_name": "Acme Industries Private Limited",
    "gstin": "29AAAPL1234C1ZV",
    "notice_type": "ASMT-10",
    "state": "Karnataka",
    "tax_period": "FY 2019-20",
    "section_invoked": "61",
    "amount_disputed": 4520000,
    "notice_date": "2024-03-11",
    "due_date": "2024-04-10",
    "issues": "1. ITC availed in excess of GSTR-2A\n2. Interest under section 50",
    "facts": "Manufacturer of industrial fasteners. Supplier-wise reconciliation available for all but three suppliers, who were non-filers for two quarters.",
    "documents_available": "GSTR-2A/3B reconciliation, purchase register, sample invoices"
  },
  "expected": {
    "position_taken": "contest",
    "position_keywords": ["limitation", "time-barred", "section 73"],
    "issues_expected": ["ITC mismatch", "interest under section 50"],
    "procedural_points": ["limitation", "73(10)"],
    "must_not_say": ["concede the entire demand"],
    "outcome": "Demand dropped at ASMT-12 stage.",
    "notes": "The limitation point was decisive. Any panel that misses it has failed this matter."
  }
}
```

Only `id`, `intake` and `expected.issues_expected` are required. The more you
fill in, the sharper the signal.

**Anonymise if you like** — the harness runs on whatever you give it. If you
would rather not put client names in the repo, replace them; the scoring does
not depend on identity. `evals/golden/` is gitignored by default.

## Running it

```bash
# Everything in the golden set, on the Pro tier
uv run python -m evals.run

# One matter, while you are iterating on a prompt
uv run python -m evals.run --only gst-001

# Compare tiers — is the draft tier good enough for research work?
uv run python -m evals.run --tier draft

# Dry run: no model calls, just checks your golden set parses
uv run python -m evals.run --dry-run
```

Results land in `evals/results/<timestamp>/`:

- `scorecard.md` — read this. Summary table, per-matter detail, and the
  human-grading questions
- `results.json` — raw output for diffing between runs
- `<matter-id>.json` — the full deliberation for each matter

## The workflow that matters

1. Run the harness. Record the baseline.
2. Change **one** thing — usually a role prompt in `backend/roles.py`.
3. Run again.
4. Compare `scorecard.md`. Did it improve, or did you just move the problem?

Changing prompts without this loop is guessing, and prompt changes that feel
better frequently score worse.

## Cost

A full run over 10 matters on the Pro tier is roughly ₹150-500 depending on
notice complexity. Run the draft tier while iterating on structure, and the Pro
tier when you are deciding whether something is genuinely better.

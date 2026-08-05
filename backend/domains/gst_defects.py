"""The GST defect catalogue.

A scrutiny or demand notice is a list of parameter-wise defects, and the
department both raises and disposes of them one at a time. This file is the
map from the heading the department prints to what that heading actually means:
which provisions are engaged, what posture the limb usually takes, and — the
part that decides matters — exactly which document the officer will demand
before dropping it.

THE EVIDENCE LIST IS THE PRODUCT
--------------------------------
In the matter this catalogue was built against, seven of eight defects were
dropped. The eighth survived to a show cause notice for one reason, stated in
the officer's own findings: the taxpayer had argued the e-invoicing mandate
correctly, but had "not provided first e-invoice for the month of august 2023
for verification." A correct legal position lost a limb because one system
report was not attached.

Every `evidence_required` entry below is written to prevent that specific
failure. They are not a generic document checklist; they name the artefact an
officer asks for when disposing of that particular defect.

DEFAULT POSTURES ARE PROPOSALS
------------------------------
`default_posture` seeds the triage so that limbs answered by arithmetic do not
convene four counsel. It is a proposal a reviewer confirms, never a decision.
Where a limb genuinely turns on analysis the default is UNDECIDED, which routes
it to the panel — that is the correct expense, and the only correct expense.
"""

import re

from ..defects import (
    AGREED_PAID,
    CONTESTED,
    EXPLAINED,
    UNDECIDED,
)


def _p(*patterns):
    return [re.compile(p, re.IGNORECASE) for p in patterns]


class DefectType:
    def __init__(self, key, label, patterns, statute="", sections=(), rules=(),
                 default_posture=UNDECIDED, evidence_required=(),
                 authority_tags=(), drafting_note="", hearing_questions=()):
        self.key = key
        self.label = label
        self.patterns = patterns
        self.statute = statute
        self.sections = list(sections)
        self.rules = list(rules)
        self.default_posture = default_posture
        self.evidence_required = list(evidence_required)
        self.authority_tags = list(authority_tags)
        self.drafting_note = drafting_note
        self.hearing_questions = list(hearing_questions)

    def as_dict(self):
        return {
            "key": self.key,
            "label": self.label,
            "statute": self.statute,
            "sections": self.sections,
            "rules": self.rules,
            "default_posture": self.default_posture,
            "evidence_required": self.evidence_required,
            "drafting_note": self.drafting_note,
            "hearing_questions": self.hearing_questions,
        }


# ---------------------------------------------------------------------------
# What the officer asks at the personal hearing
# ---------------------------------------------------------------------------
# The written reply is only half the proceeding. Section 75(4) gives a right of
# hearing wherever an adverse decision is contemplated, and the hearing is
# where small-practice representation is weakest — not because the law is not
# known but because the questions are not anticipated, and a limb that was
# answered perfectly in writing is conceded across the table by an unprepared
# answer.
#
# These are the questions officers actually put, per defect type. They are
# assembled into the hearing brief in the file note, alongside the artefact to
# carry for that limb. Deliberately phrased as the officer would put them,
# not as a topic list: "which table of GSTR-1 carries the credit note, and in
# which month" is preparable, "credit note issues" is not.
HEARING_QUESTIONS = {
    "outward_short_payment": [
        "Show me the month in which this invoice was reported, and in which "
        "table of GSTR-1.",
        "Your 3B for that month is lower than your 1. Which specific invoices "
        "account for the difference?",
        "Was any part of this difference paid later, and through which "
        "challan?",
    ],
    "turnover_difference": [
        "Take me from the turnover in the audited accounts to the turnover in "
        "GSTR-9, line by line.",
        "What is this residual difference, and which document supports it?",
        "Does this figure include any non-GST or Schedule III income? Show me "
        "where it sits in the accounts.",
    ],
    "credit_notes": [
        "Which table of GSTR-1 carries this credit note, and in which month?",
        "Has the recipient reversed the corresponding credit? What is your "
        "evidence of that?",
        "Was the credit note issued within the time limit in Section 34(2)?",
    ],
    "itc_excess_2b": [
        "Give me the supplier-wise breakup of the difference between 2B and "
        "your 3B.",
        "For each supplier: has the invoice been paid, and through what mode?",
        "Which of these differences are timing, and in which month did they "
        "reverse?",
    ],
    "itc_blocked_17_5": [
        "What was this expenditure incurred for, and how does it relate to "
        "your outward supply?",
        "Has this been capitalised? Has depreciation been claimed on the tax "
        "component?",
        "Why do you say this falls outside clause (c)/(d) of Section 17(5)?",
    ],
    "itc_time_limit": [
        "On what date was this credit taken in your 3B, and for which invoice "
        "date?",
        "Do you rely on Section 16(5) or 16(6)? For which financial year?",
        "Was the return for the relevant period filed, and on what date?",
    ],
    "itc_supplier_default": [
        "What steps did you take to satisfy yourself that this supplier had "
        "paid?",
        "Show me proof of payment to the supplier including the tax component.",
        "Has the supplier since filed? Have you obtained a certificate from "
        "them?",
    ],
    "itc_common_credit": [
        "Show me the Rule 42 working for each month of the year.",
        "What is your exempt turnover, and how has it been arrived at?",
        "Has the annual reconciliation under Rule 42(2) been carried out?",
    ],
    "itc_180_days": [
        "On what date was this supplier paid, and by what mode?",
        "If the payment is beyond 180 days, has the credit been reversed and "
        "re-availed?",
        "Show me the ledger of this supplier for the whole year.",
    ],
    "rcm": [
        "Which of these inward supplies do you accept attract reverse charge?",
        "Has the tax been paid in cash? Show me the challan.",
        "If you have taken credit of the same, in which month?",
    ],
    "einvoice": [
        "What was your aggregate turnover in the preceding financial year? "
        "Show me the working.",
        "From which date did the mandate apply to you?",
        "Show me the first e-invoice generated after that date, with its IRN "
        "and acknowledgement.",
    ],
    "eway_bill": [
        "Why was the e-way bill not generated, or why had it expired?",
        "What is the evidence that the goods are covered by a tax invoice "
        "reported in your returns?",
        "What material is there of any intent to evade tax?",
    ],
    "interest_delayed_payment": [
        "For which periods do you accept delay, and for how many days?",
        "How much of the liability was discharged in cash, and how much by "
        "credit?",
        "Do you rely on the proviso to Section 50(1)? On what basis?",
    ],
    "late_fee": [
        "What is the date of filing of each return in question?",
        "Do you rely on any amnesty or waiver notification? Which one?",
    ],
    "classification": [
        "Under which heading do you classify this, and on what reasoning?",
        "Is there any advance ruling, circular or judgment you rely on?",
        "How have you classified the same supply in earlier periods?",
    ],
    "valuation": [
        "How was the transaction value arrived at? Is the recipient a related "
        "person?",
        "What discounts have been given, and were they known at or before the "
        "time of supply?",
        "Show me the agreement governing this supply.",
    ],
    "place_of_supply": [
        "Where was the recipient located, and where were the goods delivered?",
        "Which provision of Sections 10 to 13 do you say governs this?",
        "If the tax was paid under the wrong head, has Section 77 been "
        "invoked?",
    ],
    "registration": [
        "On what date did the aggregate turnover cross the threshold?",
        "From which date have you obtained registration, and why the delay?",
    ],
    "refund_rejection": [
        "Which documents required by Rule 89 were filed with the application?",
        "Was a deficiency memo issued? On what date, and what did it say?",
        "How has the refund amount been computed?",
    ],
    "penalty_general": [
        "What is the material establishing intent, suppression or wilful "
        "misstatement?",
        "Why should penalty be levied where the tax has been paid with "
        "interest?",
    ],
}


def hearing_questions_for(key: str):
    """
    The questions to expect on a limb of this type.

    Falls back to the questions that apply to any limb rather than to nothing:
    an officer always asks what the figure is made of and what supports it, and
    a brief that says "no questions" for an unmapped defect type is worse than
    one that says the obvious.
    """
    return HEARING_QUESTIONS.get(key) or [
        "How is the amount in this limb made up? Take me through the working.",
        "Which document supports that working, and is it on record?",
        "Do you accept any part of this limb? If so, how much, and has it been "
        "paid?",
    ]


DEFECT_TYPES = [
    # -- Outward side ------------------------------------------------------
    DefectType(
        "outward_short_payment",
        "Short payment of tax on outward supplies",
        # The last three cover the Rule 88C / DRC-01B limb — the difference
        # between the liability declared in GSTR-1 and that discharged in
        # GSTR-3B. DRC-01B is issued in bulk and had no pattern at all, so the
        # whole form segmented to nothing and the notice was answered as one
        # undifferentiated issue.
        _p(r"short\s+payment.{0,40}outward", r"short\s+payment\s+of\s+tax",
           r"outward\s+turnover\s+discrepanc",
           r"difference\s+in\s+liability",
           r"liability.{0,60}gstr[\s-]*1.{0,60}gstr[\s-]*3b",
           r"\brule\s*88C\b"),
        statute="Section 73/74 read with Sections 37 and 39",
        sections=["37", "39", "73"],
        default_posture=EXPLAINED,
        evidence_required=[
            "Month-wise GSTR-1 versus GSTR-3B working for the whole year, "
            "head-wise, tying to the figures in the notice's own annexure.",
            "Where the difference is a credit note or amendment: the original "
            "tax invoice, the credit note, and the GSTR-1 table (9/11) in which "
            "the reduction was reported, with the month identified.",
            "GSTR-9 and GSTR-9C extracts showing how each statement treated the "
            "same transaction — a 9C template that does not carry a prior-year "
            "amendment is the usual cause and must be shown, not asserted.",
        ],
        drafting_note="Meet this month by month and head by head. An aggregate "
                      "answer invites the officer to confirm the aggregate.",
    ),
    DefectType(
        "turnover_difference",
        "Difference in turnover across returns and statements",
        _p(r"difference\s+in\s+turnover", r"turnover\s+(?:variance|difference|"
           r"mismatch)", r"reconcil\w+\s+the\s+turnover"),
        statute="Section 61 read with Rule 99; Sections 35(5)/44",
        sections=["44", "61"],
        default_posture=EXPLAINED,
        evidence_required=[
            "Reconciliation from audited turnover to GSTR-9C Table 5P to GSTR-9 "
            "to GSTR-1 to GSTR-3B, each bridging line separately identified.",
            "Audited financial statements for the year with the turnover note.",
            "Documentary support for every bridging line — credit notes, "
            "amendments, non-GST income, schedule III items.",
        ],
        drafting_note="Every bridging line needs its own amount and its own "
                      "document. A reconciliation with an unexplained residue "
                      "concedes that residue.",
    ),
    DefectType(
        "credit_notes",
        "Credit notes — compliance with Section 34 and Section 15(3)(b)",
        _p(r"credit\s+notes?\b", r"section\s*34\b.{0,40}credit",
           r"15\s*\(\s*3\s*\)\s*\(\s*b\s*\)"),
        statute="Section 34 read with Section 15(3)(b) and Rule 53",
        sections=["15(3)(b)", "34", "34(2)"],
        rules=["53"],
        default_posture=EXPLAINED,
        evidence_required=[
            "Credit note register for the year, each note linked to its "
            "original tax invoice number and date.",
            "Proof that each credit note was declared within the Section 34(2) "
            "window — the GSTR-1 month of declaration for each note.",
            "Confirmation that the recipient reversed the corresponding input "
            "tax credit, or that the tax incidence was not passed on.",
            "Where post-supply discount is alleged: the agreement establishing "
            "the discount was agreed at or before the time of supply, and the "
            "linkage to specific invoices. If no post-supply discount was "
            "given, say so — Section 15(3)(b) then does not arise at all.",
        ],
        drafting_note="Section 34 and Section 15(3)(b) are different tests. "
                      "Answer both, and if no post-supply discount was issued, "
                      "say so expressly rather than arguing 15(3)(b) compliance.",
    ),

    # -- Input side --------------------------------------------------------
    DefectType(
        "itc_excess_2b",
        "Excess input tax credit availed against GSTR-2B",
        # The most common defect in Indian GST practice, and the patterns
        # below were the narrowest in the catalogue. The golden set caught it:
        # a heading reading "Input tax credit availed in excess of that
        # appearing in GSTR-2B" — the department's own standard phrasing —
        # matched none of the original four patterns, because they all
        # required the words "excess" and "ITC" adjacent and in that order.
        # A limb that does not segment is a limb the reply never answers, and
        # an unanswered limb is confirmed unopposed.
        _p(r"excess\s+(?:claim|availment)\s+of\s+itc", r"itc.{0,30}w\.?r\.?t\.?"
           r"\s*gstr[\s-]*2[ab]", r"excess\s+itc\s+availed",
           r"input\s+tax\s+discrepanc",
           r"(?:itc|input\s+tax\s+credit)\s+availed\s+in\s+excess",
           r"excess\s+input\s+tax\s+credit",
           r"(?:itc|input\s+tax\s+credit).{0,50}(?:excess|exceeds|"
           r"mismatch|difference).{0,50}gstr[\s-]*2[ab]",
           r"gstr[\s-]*2[ab].{0,40}(?:vs\.?|versus|and)\s*gstr[\s-]*3b"),
        statute="Section 16(2)(aa) read with Rule 36(4); Rule 88D",
        sections=["16(2)(aa)", "16(2)(b)", "16(2)(c)", "16(2)(d)", "73"],
        rules=["36(4)", "88D"],
        default_posture=UNDECIDED,
        evidence_required=[
            "Month-wise static GSTR-2B for the entire year — not GSTR-2A, which "
            "is dynamic and is not the statutory comparator after 01.01.2022.",
            "Month-wise GSTR-3B Table 4A(5) and 4D(1) extracts.",
            "Line-by-line reconciliation bucketing the difference: reverse "
            "charge, import IGST on Bill of Entry, ISD credit, supplier timing, "
            "amendments and credit notes, supplier error, supplier non-filing, "
            "and any residue.",
            "Electronic credit ledger for the year, head-wise, to establish "
            "whether the disputed credit was ever utilised — interest under "
            "Section 50(3) with Rule 88B arises only on credit availed AND "
            "utilised.",
            "Where credit was carried into the following year: the GSTR-3B of "
            "the later period in which it was availed, tying to Table 8C/13 of "
            "GSTR-9.",
        ],
        authority_tags=["itc_2a_2b_mismatch", "itc_supplier_default"],
        drafting_note="Bucket the difference before answering it. The mechanical "
                      "categories fall away at the threshold and must not be "
                      "argued as though they were in issue.",
    ),
    DefectType(
        "itc_blocked_17_5",
        "Blocked credit under Section 17(5)",
        _p(r"ineligible\s+itc", r"17\s*\(\s*5\s*\)", r"blocked\s+credit"),
        statute="Section 17(5)",
        sections=["16(1)", "17(5)", "17(5)(a)", "17(5)(b)", "17(5)(c)",
                  "17(5)(d)", "2(119)"],
        default_posture=CONTESTED,
        evidence_required=[
            "Sample purchase invoices for each disputed commodity or service "
            "class, with HSN/SAC as classified by the department.",
            "Customer work orders or contracts establishing the output supply — "
            "where the output is a works contract to a third party, the "
            "Section 17(5)(c)/(d) bar does not reach the contractor's inputs.",
            "Project completion certificates or handover documents showing the "
            "asset vests in the customer and not in the taxpayer.",
            "For motor vehicle limbs: registration certificates establishing "
            "the vehicles carry goods, not passengers — Section 17(5)(a) "
            "restricts only vehicles for transportation of persons.",
            "For insurance limbs: the policy schedule showing the subject "
            "matter insured is project plant and equipment rather than life or "
            "health cover.",
        ],
        authority_tags=["itc_blocked_17_5", "works_contract"],
        drafting_note="Answer commodity class by commodity class with the amount "
                      "for each. Where a class is genuinely small and genuinely "
                      "weak, paying it under protest buys the credibility that "
                      "carries the large class.",
    ),
    DefectType(
        "itc_time_limit",
        "Input tax credit denied as time-barred under Section 16(4)",
        _p(r"16\s*\(\s*4\s*\)", r"time\s*[- ]?barred?\s+(?:itc|credit)",
           r"belated\s+availment"),
        statute="Section 16(4), read with Sections 16(5) and 16(6)",
        sections=["16(4)", "16(5)", "16(6)"],
        default_posture=CONTESTED,
        evidence_required=[
            "The GSTR-3B in which the credit was availed, with its filing date.",
            "Whether the year falls within FY 2017-18 to 2020-21, in which case "
            "Section 16(5) relief applies directly.",
            "Where registration was cancelled and restored: the cancellation "
            "and revocation orders, for Section 16(6).",
        ],
        authority_tags=["itc_time_limit"],
    ),
    DefectType(
        "itc_supplier_default",
        "Input tax credit denied for supplier default under Section 16(2)(c)",
        # The second pattern used to require the singular "supplier not filed"
        # with nothing between. Departments write "suppliers who have not
        # filed returns" at least as often, and that phrasing matched nothing.
        _p(r"16\s*\(\s*2\s*\)\s*\(\s*c\s*\)",
           r"supplier[s]?\b.{0,30}\bnot\s+(?:filed|paid|furnished|discharged)",
           r"non[\s-]?filer\s+supplier", r"tax\s+not\s+paid\s+"
           r"(?:to\s+)?(?:the\s+)?government"),
        statute="Section 16(2)(c) read with Section 155",
        sections=["16(2)(c)", "155"],
        default_posture=CONTESTED,
        evidence_required=[
            "Tax invoices, proof of receipt of goods or services, and proof of "
            "payment to the supplier through banking channels.",
            "E-way bills, transport documents and goods receipt records "
            "establishing the supply was genuine.",
            "The supplier's GSTR-1 filing status and any subsequent filing.",
            "Correspondence with the supplier calling on it to discharge tax.",
        ],
        authority_tags=["itc_supplier_default"],
        drafting_note="This is the exposed limb. Establish every condition "
                      "within the recipient's own control, and do the "
                      "arithmetic of contesting versus reversing before "
                      "committing the client to a fight.",
    ),
    DefectType(
        "itc_common_credit",
        "Common credit reversal under Rules 42 and 43",
        _p(r"rule\s*4[23]\b", r"common\s+credit", r"exempt\s+turnover.{0,30}"
           r"revers"),
        statute="Section 17(2) read with Rules 42 and 43",
        sections=["17(2)"],
        rules=["42", "43"],
        default_posture=UNDECIDED,
        evidence_required=[
            "Working for the annual Rule 42/43 computation with the exempt and "
            "total turnover figures used.",
            "Classification of each input as exclusively taxable, exclusively "
            "exempt, or common.",
        ],
    ),
    DefectType(
        "itc_180_days",
        "Reversal for non-payment to supplier within 180 days (Rule 37)",
        _p(r"rule\s*37\b", r"180\s*days",
           r"one\s+hundred\s+and\s+eighty\s+days",
           r"second\s+proviso.{0,30}16\s*\(\s*2"),
        statute="Second proviso to Section 16(2) read with Rule 37",
        sections=["16(2)"],
        rules=["37"],
        default_posture=EXPLAINED,
        evidence_required=[
            "Supplier ledger and bank statements evidencing payment within 180 "
            "days of the invoice date, invoice by invoice.",
            "Where payment was late: proof of re-availment in the correct "
            "period.",
        ],
    ),
    DefectType(
        "rcm",
        "Reverse charge liability short paid",
        _p(r"reverse\s+charge", r"\brcm\b", r"section\s*9\s*\(\s*[34]\s*\)"),
        statute="Section 9(3)/9(4) read with Section 31(3)(f)",
        sections=["9(3)", "9(4)", "31(3)(f)"],
        default_posture=UNDECIDED,
        evidence_required=[
            "Schedule of inward supplies liable to reverse charge, by category "
            "and month, with the notification relied on for each.",
            "Self-invoices issued under Section 31(3)(f).",
            "GSTR-3B Table 3.1(d) and Table 4A(3) extracts showing the "
            "liability discharged and the credit taken.",
        ],
        drafting_note="Where the tax was paid and the credit taken in the same "
                      "period the exercise is revenue neutral. Say so and "
                      "quantify it.",
    ),

    # -- Interest, fees and penalties --------------------------------------
    DefectType(
        "late_fee",
        "Late fee for belated returns",
        _p(r"late\s+fee", r"section\s*47\b", r"filed\s+belatedly"),
        statute="Section 47(1) read with Section 37 and Rule 59",
        sections=["37", "47(1)"],
        rules=["59"],
        default_posture=AGREED_PAID,
        evidence_required=[
            "Filing dates and due dates for each return said to be late.",
            "DRC-03 challan where the late fee has been discharged.",
        ],
        drafting_note="Arithmetic, not argument. Verify the day count and the "
                      "rate, pay it, and cite the payment reference.",
    ),
    DefectType(
        "interest_delayed_payment",
        "Interest on delayed payment of tax",
        # "Interest PAYABLE on delayed payment" is how the portal prints this
        # heading, and the original pattern required "interest on delayed"
        # with nothing between. Caught by the golden set.
        _p(r"interest\s+on\s+(?:delayed|belated)", r"section\s*50\s*\(\s*1\s*\)",
           r"interest\s+on\s+invoice\s+value\s+increased",
           r"interest.{0,30}amendment",
           r"interest\s+(?:payable|leviable|liable|chargeable)"
           r".{0,30}(?:delayed|belated|late)",
           r"non[\s-]*payment\s+of\s+interest"),
        # NOTE: do not add a bare "interest under section 50" pattern here.
        # It was tried, and it matches the demand boilerplate carried by
        # almost every notice — "...along with interest under Section 50 and
        # penalty under Section 73(9)" — which grew a phantom interest limb on
        # four of the eight golden cases, one of which then claimed the whole
        # notice's total as its own figure and doubled the matter.
        statute="Section 50(1) read with Rule 88B",
        sections=["50(1)", "50(3)"],
        rules=["88B"],
        default_posture=AGREED_PAID,
        evidence_required=[
            "Working of the delay in days against the statutory due date for "
            "each transaction.",
            "Where the tax sat in the electronic cash ledger before the return "
            "was filed, the ledger extract — Rule 88B measures interest on the "
            "portion discharged from the cash ledger.",
            "DRC-03 challan where interest has been discharged.",
        ],
    ),
    DefectType(
        "einvoice",
        "Non-compliance with e-invoicing under Rule 48(4)",
        # The leading \b is load-bearing. Without it "e[\s-]?invoic" matches
        # the ordinary English phrase "th|e invoic|e" — so every notice using
        # the words "the invoice", which is very nearly all of them, grew a
        # spurious e-invoicing limb with a neighbouring limb's figures
        # attached. Caught by the golden set on an RFD-08 whose second limb
        # read "not accompanied by the invoice-wise details".
        _p(r"\be[\s-]?invoic", r"rule\s*48\s*\(\s*[45]\s*\)", r"\birn\b",
           r"invoice\s+registration\s+portal"),
        statute="Rule 48(4) and 48(5) read with Section 125",
        sections=["2(6)", "122", "125", "126"],
        rules=["48(4)", "48(5)"],
        default_posture=CONTESTED,
        evidence_required=[
            "Aggregate turnover under Section 2(6) for every preceding "
            "financial year from 2017-18, across ALL GSTINs on the same PAN, "
            "with the GSTR-9/9C extract proving each figure. This fixes which "
            "notification slab applies and therefore the date the obligation "
            "began.",
            "THE IRP PORTAL DATA REPORT FOR THE FIRST MONTH OF MANDATORY "
            "APPLICABILITY, listing every B2B invoice with its IRN and status. "
            "This is the document officers ask for and it is the document "
            "taxpayers omit. A correct legal position on the applicable date "
            "does not survive without it.",
            "GSTR-1 for that first month showing the e-invoice data "
            "auto-populated without error.",
            "Where any invoice within the mandate genuinely lacks an IRN: the "
            "count, the value, and whether tax on it was otherwise discharged.",
        ],
        authority_tags=["penalty_general", "minor_breach"],
        drafting_note="Two limbs, and both must be proved: the mandate began on "
                      "the date the taxpayer's own turnover slab says it began, "
                      "AND every invoice from that date carries an IRN. The "
                      "second limb is proved only by the portal report.",
    ),
    DefectType(
        "penalty_general",
        "General penalty proposed under Section 125",
        _p(r"section\s*125\b", r"general\s+penalt"),
        statute="Section 125 read with Section 126",
        sections=["125", "126"],
        default_posture=CONTESTED,
        evidence_required=[
            "Identification of the specific provision said to be contravened — "
            "Section 125 is predicated on a proven contravention and cannot "
            "stand on a general assertion.",
            "Evidence that the breach, if any, caused no loss of revenue, for "
            "Section 126(1).",
        ],
        authority_tags=["penalty_general", "minor_breach"],
    ),
    DefectType(
        "eway_bill",
        "E-way bill contravention and penalty",
        _p(r"e[\s-]?way\s*bill", r"section\s*129\b", r"\bMOV[\s-]?\d"),
        statute="Section 129 read with Rule 138",
        sections=["122", "126", "129", "130"],
        rules=["138"],
        default_posture=CONTESTED,
        evidence_required=[
            "The e-way bill, tax invoice and transport document for the "
            "consignment.",
            "Evidence on whether the defect was clerical and whether any intent "
            "to evade is alleged with particulars.",
        ],
        authority_tags=["eway_bill"],
    ),

    # -- Classification, valuation, place of supply ------------------------
    DefectType(
        "classification",
        "Classification or rate dispute",
        _p(r"classification", r"\bhsn\b.{0,30}(?:incorrect|wrong|mis)",
           r"rate\s+of\s+tax.{0,30}(?:incorrect|wrong|applicable)"),
        statute="Section 9 read with the rate notifications and the Tariff",
        sections=["9"],
        default_posture=CONTESTED,
        evidence_required=[
            "Product literature, technical specifications and end-use evidence.",
            "The rate notification entry relied on, with its effective date.",
            "Any advance ruling, circular or judicial authority on the same "
            "goods or services.",
        ],
        authority_tags=["classification"],
    ),
    DefectType(
        "valuation",
        "Valuation dispute",
        _p(r"valuation", r"section\s*15\s*\(\s*[12]\s*\)",
           r"transaction\s+value", r"related\s+(?:person|part(?:y|ies))",
           r"\brule\s*28\b", r"open\s+market\s+value"),
        statute="Section 15 read with the Valuation Rules",
        sections=["15"],
        default_posture=CONTESTED,
        evidence_required=[
            "The contract or purchase order establishing the agreed "
            "consideration.",
            "Evidence on relationship between the parties where related-party "
            "valuation is alleged.",
        ],
    ),
    DefectType(
        "place_of_supply",
        "Place of supply and wrong-head tax",
        _p(r"place\s+of\s+supply", r"section\s*1[０0]\s*(?:of\s+)?(?:the\s+)?igst",
           r"wrong\s+head", r"section\s*77\b"),
        statute="Sections 10 to 13 of the IGST Act; Section 77 CGST / Section 19 IGST",
        sections=["77"],
        default_posture=CONTESTED,
        evidence_required=[
            "Contracts and invoices showing the location of supplier and "
            "recipient and the nature of the supply.",
            "Where tax was paid under the wrong head: proof of that payment, "
            "for the Section 77 / Section 19 refund route.",
        ],
        authority_tags=["place_of_supply"],
    ),

    # -- Procedural --------------------------------------------------------
    DefectType(
        "registration",
        "Registration — cancellation or suspension proposed",
        _p(r"cancellation\s+of\s+registration", r"section\s*29\b",
           r"\bREG[\s-]?1[78]\b"),
        statute="Section 29 read with Rule 22",
        sections=["29", "30"],
        rules=["22"],
        default_posture=CONTESTED,
        evidence_required=[
            "Proof of existence and business activity at the principal place — "
            "rent agreement, utility bills, photographs, bank statements.",
            "Return filing status and any returns filed after the notice.",
        ],
        authority_tags=["registration"],
    ),
    DefectType(
        "refund_rejection",
        "Refund rejection proposed",
        # A bare "refund" was too broad: it matched the Section 73 boilerplate
        # "tax not paid or short paid or erroneously refunded", so every s.73
        # demand grew a refund limb. Refund must be the SUBJECT of the phrase.
        # Rule 89 is included because a refund limb often argues the
        # documentation requirement without using the word at all.
        _p(r"\brefund\s+(?:claim|application|of|order|reject|sanction|is\b)",
           r"rejection\s+of\s+.{0,30}refund",
           r"\brefund\b.{0,20}(?:inadmissible|not\s+admissible|rejected)",
           r"\bRFD[\s-]?0?[689]\b", r"section\s*54\b", r"rule\s*89\b"),
        statute="Section 54 read with Rules 89 to 96",
        sections=["54", "54(1)", "56"],
        rules=["89", "92(3)"],
        default_posture=CONTESTED,
        evidence_required=[
            "The refund application with its ARN and the relevant date relied "
            "on for limitation under Section 54(1).",
            "Shipping bills, BRC/FIRC or LUT as applicable to the refund class.",
            "The inverted duty computation where Rule 89(5) is in issue.",
        ],
        authority_tags=["refund"],
    ),
    DefectType(
        "other",
        "Other discrepancy",
        _p(r"^other\b"),
        statute="As specified in the notice",
        default_posture=UNDECIDED,
        evidence_required=[
            "The department's own working for this limb, and the documents it "
            "identifies as required.",
        ],
    ),
]

DEFECT_TYPES_BY_KEY = {d.key: d for d in DEFECT_TYPES}


def defect_type(key: str):
    return DEFECT_TYPES_BY_KEY.get(key) or DEFECT_TYPES_BY_KEY["other"]


def evidence_for(key: str):
    return list(defect_type(key).evidence_required)

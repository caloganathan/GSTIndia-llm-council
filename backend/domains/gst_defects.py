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
                 authority_tags=(), drafting_note=""):
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
        }


DEFECT_TYPES = [
    # -- Outward side ------------------------------------------------------
    DefectType(
        "outward_short_payment",
        "Short payment of tax on outward supplies",
        _p(r"short\s+payment.{0,40}outward", r"short\s+payment\s+of\s+tax",
           r"outward\s+turnover\s+discrepanc"),
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
        _p(r"excess\s+(?:claim|availment)\s+of\s+itc", r"itc.{0,30}w\.?r\.?t\.?"
           r"\s*gstr[\s-]*2[ab]", r"excess\s+itc\s+availed",
           r"input\s+tax\s+discrepanc"),
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
        _p(r"16\s*\(\s*2\s*\)\s*\(\s*c\s*\)", r"supplier\s+(?:has\s+)?not\s+"
           r"(?:filed|paid)", r"non[\s-]?filer\s+supplier", r"tax\s+not\s+paid\s+"
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
        _p(r"rule\s*37\b", r"180\s*days", r"second\s+proviso.{0,30}16\s*\(\s*2"),
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
        _p(r"interest\s+on\s+(?:delayed|belated)", r"section\s*50\s*\(\s*1\s*\)",
           r"interest\s+on\s+invoice\s+value\s+increased",
           r"interest.{0,30}amendment"),
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
        _p(r"e[\s-]?invoic", r"rule\s*48\s*\(\s*[45]\s*\)", r"\birn\b",
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
           r"transaction\s+value"),
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
        _p(r"refund", r"\bRFD[\s-]?0?[689]\b", r"section\s*54\b"),
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

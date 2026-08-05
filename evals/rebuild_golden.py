"""Rebuild the golden set from the specification the tests carry.

The original nine cases were never committed (evals/golden/*.json is
gitignored), so they are reconstructed here from what tests/test_golden_set.py
and tests/test_api_practice.py assert about them. Every case is invented:
no client matter is involved.
"""

import json
import pathlib

OUT = pathlib.Path.home() / "src/GSTIndia-llm-council/evals/golden"


def row(sgst=0, cgst=0, igst=0, cess=0):
    """A head-wise annexure row, printed as the department prints it."""
    total = sgst + cgst + igst + cess
    return (f"SGST {sgst:,}  CGST {cgst:,}  IGST {igst:,}  CESS {cess:,}  "
            f"Total {total:,}")


def heads(sgst=0, cgst=0, igst=0, cess=0):
    out = {}
    for key, value in (("sgst", sgst), ("cgst", cgst),
                       ("igst", igst), ("cess", cess)):
        if value:
            out[key] = float(value)
    return out


CASES = []


def case(**kwargs):
    CASES.append(kwargs)


# ---------------------------------------------------------------------------
# 1. ASMT-10 — the reference notice. tests/test_api_practice.py pins this one:
#    exactly eight limbs, and an amount_disputed of 317450.
# ---------------------------------------------------------------------------

ASMT10_TEXT = f"""GOVERNMENT OF TAMIL NADU
COMMERCIAL TAXES DEPARTMENT
Office of the Assistant Commissioner (ST), Hosur (North) Circle

FORM GST ASMT-10
[See rule 99(1)]
Notice for intimating discrepancies in the return after scrutiny

Reference No.: ZD330226255583F   Date: 12.02.2026

To
M/s. KAVERI AUTOCOMP PRIVATE LIMITED
PLOT 42, SIPCOT INDUSTRIAL COMPLEX, HOSUR - 635109

GSTIN: 33AABCK4521M1ZR
Financial Year: 2023-24
Section under which notice is issued: 61
Date by which reply has to be submitted: 13.03.2026

On scrutiny of the returns furnished by you for the period stated above, the
discrepancies set out below have been noticed. The head-wise amount for each
parameter is stated against it.

Output turnover discrepancies

• Short payment of tax on outward supplies:
The taxable value reported in your monthly returns falls short of the value
reported in the statement of outward supplies for the same months. The
resultant liability, head-wise, is as follows.
{row(sgst=12500, cgst=12500)}

• Difference in turnover between the annual return and the audited accounts:
The turnover certified in the reconciliation statement does not agree with the
turnover declared in the annual return. The unexplained portion is as follows.
{row(sgst=9000, cgst=9000)}

• Credit notes declared beyond the window in Section 34(2):
Credit notes reducing your outward liability appear to have been declared after
the statutory window had closed. The liability so reduced is as follows.
{row(sgst=15750, cgst=15750)}

Input tax credit discrepancies

• Input tax credit availed in excess of that appearing in GSTR-2B:
The credit taken in your returns exceeds the credit auto-populated for the same
months, and the conditions in Section 16(2)(aa) do not appear to be satisfied.
{row(sgst=41000, cgst=41000, igst=8000)}

• Claim of ineligible ITC under Section 17(5):
Credit appears to have been availed on goods and services on which credit is
restricted. The amount so availed is as follows.
{row(sgst=22300, cgst=22300)}

• Reverse charge liability short paid on inward supplies:
Inward supplies liable to tax on reverse charge basis appear not to have been
offered to tax in full. The shortfall is as follows.
{row(sgst=17000, cgst=17000)}

Other parameters

• Non-compliance with e-invoicing under Rule 48(4):
Your aggregate turnover in the preceding year appears to have crossed the
notified threshold, and invoices issued thereafter do not carry an invoice
reference number. The tax on such invoices is as follows.
{row(sgst=25000, cgst=25000)}

• Late fee for belated filing of the annual return:
The annual return for the year was filed after the due date. The late fee
computed under Section 47 is as follows.
{row(sgst=12175, cgst=12175)}

You are requested to explain the above discrepancies. Should you find the
liability acceptable in whole or in part, you may pay it with applicable
interest and intimate this office.

Signature
Name: R. SUNDARAM
Designation: Assistant Commissioner (ST)
Jurisdiction: Hosur (North) , HOSUR , Tamil Nadu
"""

case(
    id="gst-asmt10-multilimb-fy2324",
    synthetic=True,
    provenance=(
        "Invented. Reconstructed from the assertions in "
        "tests/test_golden_set.py and tests/test_api_practice.py, which pin "
        "this notice at eight limbs totalling Rs. 3,17,450. The entity, GSTIN, "
        "reference, officer and addresses are fabricated; the heading language "
        "follows the Tamil Nadu scrutiny attachment, because the heading "
        "phrasing is what the catalogue is being tested against."
    ),
    description=(
        "Eight-limb scrutiny notice spanning the outward side, the input side "
        "and the residual parameters — the shape a reply must answer limb by "
        "limb."
    ),
    notice_text=ASMT10_TEXT,
    intake={
        "client_name": "KAVERI AUTOCOMP PRIVATE LIMITED",
        "gstin": "33AABCK4521M1ZR",
        "notice_type": "ASMT-10",
        "state": "Tamil Nadu",
        "tax_period": "FY 2023-24",
        "section_invoked": "61",
        "notice_date": "2026-02-12",
        "due_date": "2026-03-13",
        "amount_disputed": 317450,
        "facts": (
            "Tier-2 automotive component manufacturer. Books, supplier-wise "
            "reconciliations and the credit note register are complete. Two "
            "suppliers were non-filers for one quarter."
        ),
        "documents_available": (
            "GSTR-1/3B/2B monthly extracts, annual return and reconciliation "
            "statement, credit note register, purchase register, electronic "
            "credit ledger"
        ),
        "defects": [
            {"index": 1, "type": "outward_short_payment",
             "heading": "Short payment of tax on outward supplies",
             "amount_by_head": heads(sgst=12500, cgst=12500)},
            {"index": 2, "type": "turnover_difference",
             "heading": "Difference in turnover",
             "amount_by_head": heads(sgst=9000, cgst=9000)},
            {"index": 3, "type": "credit_notes",
             "heading": "Credit notes beyond Section 34(2)",
             "amount_by_head": heads(sgst=15750, cgst=15750)},
            {"index": 4, "type": "itc_excess_2b",
             "heading": "ITC availed in excess of GSTR-2B",
             "amount_by_head": heads(sgst=41000, cgst=41000, igst=8000)},
            {"index": 5, "type": "itc_blocked_17_5",
             "heading": "Ineligible ITC under Section 17(5)",
             "amount_by_head": heads(sgst=22300, cgst=22300)},
            {"index": 6, "type": "rcm",
             "heading": "Reverse charge short paid",
             "amount_by_head": heads(sgst=17000, cgst=17000)},
            {"index": 7, "type": "einvoice",
             "heading": "Non-compliance with e-invoicing",
             "amount_by_head": heads(sgst=25000, cgst=25000)},
            {"index": 8, "type": "late_fee",
             "heading": "Late fee on the annual return",
             "amount_by_head": heads(sgst=12175, cgst=12175)},
        ],
    },
    expected={
        "position_taken": "contest",
        "position_keywords": ["GSTR-2B", "reconciliation", "Section 16(2)(aa)",
                              "Rule 48(4)"],
        "issues_expected": ["ITC mismatch", "credit notes", "e-invoicing",
                            "reverse charge"],
        "procedural_points": ["61", "75(4)"],
        "must_not_say": ["concede the entire demand"],
        "outcome": (
            "Six limbs dropped on reconciliation. The e-invoicing limb "
            "survived to a show cause notice because the portal report for the "
            "first month of applicability was not filed with the reply."
        ),
        "notes": (
            "The e-invoicing limb is the one that decides this matter, and it "
            "is decided by a document rather than by an argument."
        ),
    },
    expected_defects=[
        {"index": 1, "posture": "explained",
         "why": "Month-by-month working closes the gap."},
        {"index": 2, "posture": "explained",
         "why": "Bridging schedule from audited turnover to the annual return."},
        {"index": 3, "posture": "explained",
         "required_evidence_that_was_missing": [
             "GSTR-1 month of declaration for each credit note, proving the "
             "Section 34(2) window was met."]},
        {"index": 4, "posture": "contested",
         "required_evidence_that_was_missing": [
             "Month-wise static GSTR-2B for the whole year — not GSTR-2A.",
             "Electronic credit ledger showing the disputed credit was never "
             "utilised, which is what Rule 88B measures interest on."]},
        {"index": 5, "posture": "contested",
         "why": "Credit relates to plant and machinery, outside 17(5)(c)/(d)."},
        {"index": 6, "posture": "explained",
         "why": "Tax paid and credit taken in the same period; revenue neutral."},
        {"index": 7, "posture": "contested",
         "required_evidence_that_was_missing": [
             "IRP portal data report for the first month of mandatory "
             "applicability, listing every B2B invoice with its IRN."]},
        {"index": 8, "posture": "agreed_paid",
         "why": "Arithmetic. Verify the day count, pay, cite the challan."},
    ],
)


# ---------------------------------------------------------------------------
# 2. DRC-01 — show cause notice invoking Section 74
# ---------------------------------------------------------------------------

DRC01_TEXT = f"""GOVERNMENT OF KARNATAKA
COMMERCIAL TAXES DEPARTMENT
Office of the Deputy Commissioner of Commercial Taxes, Peenya Division

FORM GST DRC-01
[See rule 142(1)]
Summary of show cause notice

Reference No.: ZK290226118427Q   Date: 04.02.2026

To
M/s. SHREYAS PRECISION TOOLS PRIVATE LIMITED
UNIT 7, PEENYA INDUSTRIAL AREA PHASE II, BENGALURU - 560058

GSTIN: 29AAGCS7734L1ZP
Financial Year: 2020-21
Section under which notice is issued: 74
Date by which reply has to be submitted: 06.03.2026

Whereas it appears that tax has not been paid by you for the period stated
above, the grounds on which the proposed demand rests are set out below.

• Input tax credit availed from suppliers who have not filed returns:
Verification discloses that the suppliers named in the annexure did not
discharge the tax collected from you, and the condition in Section 16(2)(c) is
therefore not satisfied. The credit involved is as follows.
{row(sgst=92250, cgst=92250)}

• Credit availed beyond the time limit in Section 16(4):
Credit pertaining to invoices of the preceding year appears to have been taken
in a return furnished after the date prescribed. The credit involved is as
follows.
{row(sgst=30000, cgst=30000)}

• Suppression of outward supplies detected on comparison with e-way bill data:
Consignments moved under e-way bills generated on your portal login are not
traceable to any invoice reported in your statement of outward supplies for the
corresponding months. The tax on such consignments is as follows.
{row(sgst=45000, cgst=45000)}

You are hereby called upon to show cause why the amount stated above should not
be demanded from you together with interest and penalty.

Signature
Name: K. VIJAYALAKSHMI
Designation: Deputy Commissioner of Commercial Taxes
Jurisdiction: Peenya Division , BENGALURU , Karnataka
"""

case(
    id="gst-drc01-s74-suppression",
    synthetic=True,
    provenance=(
        "Invented. Written to exercise the three limbs on which an extended-"
        "period demand is usually built — supplier default, time limit, and an "
        "e-way bill comparison — none of which is drawn from any client "
        "matter. Entity, GSTIN, reference and officer are fabricated."
    ),
    description=(
        "Section 74 show cause notice where the extended period is invoked on "
        "an e-way bill comparison and the ingredients of suppression are "
        "asserted rather than particularised."
    ),
    notice_text=DRC01_TEXT,
    intake={
        "client_name": "SHREYAS PRECISION TOOLS PRIVATE LIMITED",
        "gstin": "29AAGCS7734L1ZP",
        "notice_type": "DRC-01",
        "state": "Karnataka",
        "tax_period": "FY 2020-21",
        "section_invoked": "74",
        "notice_date": "2026-02-04",
        "due_date": "2026-03-06",
        "amount_disputed": 334500,
        "facts": (
            "Precision machining job work. Payments to all suppliers made "
            "through banking channels with tax component. Two suppliers have "
            "since filed their outward statements for the periods in question."
        ),
        "documents_available": (
            "Tax invoices, bank statements, e-way bills, goods receipt notes, "
            "supplier ledgers, GSTR-3B filing history"
        ),
        "defects": [
            {"index": 1, "type": "itc_supplier_default",
             "heading": "ITC from suppliers who have not filed",
             "amount_by_head": heads(sgst=92250, cgst=92250)},
            {"index": 2, "type": "itc_time_limit",
             "heading": "Credit beyond Section 16(4)",
             "amount_by_head": heads(sgst=30000, cgst=30000)},
            {"index": 3, "type": "eway_bill",
             "heading": "Suppression alleged on e-way bill comparison",
             "amount_by_head": heads(sgst=45000, cgst=45000)},
        ],
    },
    expected={
        "position_taken": "contest",
        "position_keywords": ["Section 16(2)(c)", "Section 155", "16(5)",
                              "suppression", "extended period"],
        "issues_expected": ["supplier default", "time-barred credit",
                            "e-way bill variance"],
        "procedural_points": ["74", "74(1)", "limitation"],
        "must_not_say": ["accept that suppression is established"],
        "outcome": (
            "Section 74 held not made out for want of particulars; demand "
            "recast under Section 73 and the time-limit limb dropped under "
            "Section 16(5)."
        ),
        "notes": (
            "The whole matter turns on whether suppression was particularised. "
            "A panel that argues only the merits of each limb has lost the "
            "point that decides all three."
        ),
    },
    expected_defects=[
        {"index": 1, "posture": "contested",
         "required_evidence_that_was_missing": [
             "Proof of payment to each supplier through banking channels, "
             "including the tax component.",
             "Correspondence calling on the supplier to discharge the tax."]},
        {"index": 2, "posture": "contested",
         "why": "FY 2020-21 falls squarely within the Section 16(5) window."},
        {"index": 3, "posture": "contested",
         "required_evidence_that_was_missing": [
             "Consignment-wise tie-up of each e-way bill to the tax invoice "
             "and the month in which it was reported."]},
    ],
)


# ---------------------------------------------------------------------------
# 3. DRC-01A — pre-SCN intimation
# ---------------------------------------------------------------------------

DRC01A_TEXT = f"""GOVERNMENT OF MAHARASHTRA
DEPARTMENT OF GOODS AND SERVICES TAX
Office of the State Tax Officer, Andheri Nodal Division

FORM GST DRC-01A
[See rule 142(1A)]
Intimation of tax ascertained as being payable

Reference No.: ZM270226904471H   Date: 20.01.2026

To
M/s. VIRAJ POLYMERS LIMITED
GAT 118, MIDC AMBAD, NASHIK - 422010

GSTIN: 27AACCV8812K1ZT
Financial Year: 2022-23
Section under which notice is issued: 73
Date by which reply has to be submitted: 19.02.2026

The following amounts have been ascertained as payable by you on the basis of
the returns furnished. You may discharge the same before a show cause notice is
issued.

• Excess claim of ITC availed w.r.t GSTR-2B:
The credit taken in your monthly returns exceeds the credit auto-populated in
the corresponding statement for the same tax periods. The excess is as follows.
{row(sgst=61000, cgst=61000)}

• Interest payable on delayed payment of tax:
Returns for four tax periods were furnished after the prescribed date and the
liability for those periods was discharged with the belated returns. The
interest so computed is as follows.
{row(sgst=7150, cgst=7150)}

If the ascertainment is acceptable, you may pay the amount and intimate this
office in Part B of this form.

Signature
Name: S. P. DESHMUKH
Designation: State Tax Officer
Jurisdiction: Andheri Nodal Division , MUMBAI , Maharashtra
"""

case(
    id="gst-drc01a-itc-2b-mismatch",
    synthetic=True,
    provenance=(
        "Invented. A deliberately ordinary pre-show-cause intimation: the "
        "commonest defect in practice paired with an interest limb, so the "
        "catalogue is tested on the phrasing the portal actually prints "
        "('interest payable on delayed payment') rather than on a paraphrase. "
        "No client matter involved."
    ),
    description=(
        "Pre-SCN intimation on a GSTR-2B mismatch, most of which is timing "
        "rather than ineligibility."
    ),
    notice_text=DRC01A_TEXT,
    intake={
        "client_name": "VIRAJ POLYMERS LIMITED",
        "gstin": "27AACCV8812K1ZT",
        "notice_type": "DRC-01A",
        "state": "Maharashtra",
        "tax_period": "FY 2022-23",
        "section_invoked": "73",
        "notice_date": "2026-01-20",
        "due_date": "2026-02-19",
        "amount_disputed": 136300,
        "facts": (
            "Polymer compounding unit. The bulk of the difference is credit "
            "appearing in the following year's statement, reconciled and "
            "documented. Interest on the belated periods is not disputed."
        ),
        "documents_available": (
            "Month-wise GSTR-2B, GSTR-3B Table 4 extracts, supplier-wise "
            "reconciliation, electronic cash and credit ledgers, challans"
        ),
        "defects": [
            {"index": 1, "type": "itc_excess_2b",
             "heading": "Excess ITC against GSTR-2B",
             "amount_by_head": heads(sgst=61000, cgst=61000)},
            {"index": 2, "type": "interest_delayed_payment",
             "heading": "Interest on delayed payment",
             "amount_by_head": heads(sgst=7150, cgst=7150)},
        ],
    },
    expected={
        "position_taken": "partial",
        "position_keywords": ["timing", "GSTR-2B", "Rule 88B", "Table 8C"],
        "issues_expected": ["ITC mismatch", "interest"],
        "procedural_points": ["73(5)", "73(6)"],
        "must_not_say": ["dispute the interest limb"],
        "outcome": (
            "Interest limb paid at the pre-SCN stage; the credit limb was "
            "reconciled as timing and no show cause notice followed."
        ),
        "notes": (
            "Paying the small arithmetic limb at DRC-01A stage is what buys "
            "the credibility that carries the large one. A panel that contests "
            "both has misread the stage the matter is at."
        ),
    },
    expected_defects=[
        {"index": 1, "posture": "explained",
         "required_evidence_that_was_missing": [
             "GSTR-3B of the later period in which the credit was availed, "
             "tying to Table 8C of the annual return."]},
        {"index": 2, "posture": "agreed_paid",
         "why": "Arithmetic. Pay under Section 73(5) and cite the challan."},
    ],
)


# ---------------------------------------------------------------------------
# 4. RFD-08 — two refund objections. Keyed by index, not by type: both limbs
#    are refund_rejection, which is what caught the type-keying bug.
# ---------------------------------------------------------------------------

RFD08_TEXT = f"""GOVERNMENT OF GUJARAT
DEPARTMENT OF GOODS AND SERVICES TAX
Office of the Assistant Commissioner of State Tax, Surat Unit 4

FORM GST RFD-08
[See rule 92(3)]
Notice for rejection of application for refund

Reference No.: ZG240226663318M   Date: 28.01.2026

To
M/s. NIRANTAR TEXTILES LIMITED
SURVEY 214, PANDESARA GIDC, SURAT - 394221

GSTIN: 24AAECN5590J1ZW
Financial Year: 2024-25
Section under which notice is issued: 54
Date by which reply has to be submitted: 12.02.2026

Your application for refund of unutilised credit has been examined and the
following objections arise.

• Refund claim is inadmissible for want of the documents in Rule 89(2):
The statement of invoices and the certified working accompanying the
application do not cover the whole of the period claimed. The amount affected
is as follows.
{row(igst=250000)}

• Refund application is barred by limitation under Section 54(1):
A part of the claim relates to a period falling beyond two years from the
relevant date reckoned in terms of the Explanation to that provision. The
amount so affected is as follows.
{row(igst=120000)}

You are hereby called upon to furnish a reply within the time stated above,
failing which the application will be disposed of on the material on record.

Signature
Name: H. B. PATEL
Designation: Assistant Commissioner of State Tax
Jurisdiction: Surat Unit 4 , SURAT , Gujarat
"""

case(
    id="gst-rfd08-two-grounds",
    synthetic=True,
    provenance=(
        "Invented. Written specifically because one form can raise two limbs "
        "of the same catalogue type, which is the case that breaks any scorer "
        "keying limbs by type instead of by index. Entity, GSTIN and reference "
        "are fabricated."
    ),
    description=(
        "Refund rejection notice raising two distinct objections to one "
        "application — documentation and limitation."
    ),
    notice_text=RFD08_TEXT,
    intake={
        "client_name": "NIRANTAR TEXTILES LIMITED",
        "gstin": "24AAECN5590J1ZW",
        "notice_type": "RFD-08",
        "state": "Gujarat",
        "tax_period": "FY 2024-25",
        "section_invoked": "54",
        "notice_date": "2026-01-28",
        "due_date": "2026-02-12",
        "amount_disputed": 370000,
        "facts": (
            "Exporter of made-up textiles under LUT. The statement of invoices "
            "was filed in full; the portal truncated the annexure on upload, "
            "which the acknowledgement shows."
        ),
        "documents_available": (
            "Refund application with ARN, shipping bills, FIRCs, LUT, "
            "statement of invoices, portal acknowledgement"
        ),
        "defects": [
            {"index": 1, "type": "refund_rejection",
             "heading": "Documents under Rule 89(2) said to be wanting",
             "amount_by_head": heads(igst=250000)},
            {"index": 2, "type": "refund_rejection",
             "heading": "Limitation under Section 54(1)",
             "amount_by_head": heads(igst=120000)},
        ],
    },
    expected={
        "position_taken": "contest",
        "position_keywords": ["relevant date", "Rule 89(2)", "deficiency memo",
                              "Section 54(1)"],
        "issues_expected": ["refund documentation", "limitation"],
        "procedural_points": ["92(3)", "54(1)", "deficiency memo"],
        "must_not_say": ["withdraw the application and refile"],
        "outcome": (
            "Documentation objection dropped on production of the portal "
            "acknowledgement; the limitation objection was decided on the "
            "relevant date and the refund sanctioned in full."
        ),
        "notes": (
            "Two limbs of one type on one form. A reply that answers 'the "
            "refund objection' as a single issue leaves one of them "
            "unopposed."
        ),
    },
    expected_defects=[
        {"index": 1, "posture": "contested",
         "required_evidence_that_was_missing": [
             "The portal acknowledgement listing every document uploaded with "
             "the application, and any deficiency memo issued."]},
        {"index": 2, "posture": "contested",
         "why": "The relevant date for an export refund is not the invoice "
                "date, and the claim is within time on the correct reckoning."},
    ],
)


# ---------------------------------------------------------------------------
# 5. ADT-02 — audit findings
# ---------------------------------------------------------------------------

ADT02_TEXT = f"""GOVERNMENT OF TELANGANA
COMMERCIAL TAXES DEPARTMENT
Office of the Joint Commissioner (ST), Audit Division, Hyderabad

FORM GST ADT-02
[See rule 101(5)]
Audit report under Section 65(6)

Reference No.: ZT360226557902B   Date: 09.02.2026

To
M/s. DECCAN AGRO FOODS LIMITED
PLOT 88, JEEDIMETLA INDUSTRIAL ESTATE, HYDERABAD - 500055

GSTIN: 36AABCD3391F1ZQ
Financial Year: 2021-22
Section under which notice is issued: 65
Date by which reply has to be submitted: 11.03.2026

The audit of your records for the period stated above has been completed and
the findings are communicated below.

• Common credit not reversed under Rule 42:
Credit attributable to exempt outward supplies appears not to have been
reversed on the monthly basis prescribed, and the annual reconciliation does
not appear to have been carried out. The amount involved is as follows.
{row(sgst=26000, cgst=26000)}

• Classification of goods adopted at a rate lower than that applicable:
The goods described in the annexure appear to fall under a heading attracting a
higher rate than that adopted by you. The differential tax is as follows.
{row(sgst=88000, cgst=88000)}

• Reversal under Rule 37 for non-payment within 180 days:
Consideration for the invoices listed in the annexure does not appear to have
been paid to the supplier within the period prescribed. The credit to be
reversed is as follows.
{row(sgst=9500, cgst=9500)}

You may furnish your reply to the above findings within the time stated.

Signature
Name: M. RAGHAVENDRA
Designation: Joint Commissioner (ST), Audit
Jurisdiction: Audit Division , HYDERABAD , Telangana
"""

case(
    id="gst-adt02-audit-findings",
    synthetic=True,
    provenance=(
        "Invented. The classification limb was written to be genuinely "
        "arguable in both directions rather than to be won, so the set is not "
        "made up entirely of matters the taxpayer takes. No client matter "
        "involved."
    ),
    description=(
        "Audit report raising a Rule 42 reversal, a classification dispute "
        "and a Rule 37 reversal."
    ),
    notice_text=ADT02_TEXT,
    intake={
        "client_name": "DECCAN AGRO FOODS LIMITED",
        "gstin": "36AABCD3391F1ZQ",
        "notice_type": "ADT-02",
        "state": "Telangana",
        "tax_period": "FY 2021-22",
        "section_invoked": "65",
        "notice_date": "2026-02-09",
        "due_date": "2026-03-11",
        "amount_disputed": 247000,
        "facts": (
            "Food processing unit with both taxable and exempt outward "
            "supplies. Rule 42 workings exist monthly but the annual "
            "reconciliation was not documented. Classification follows a "
            "ruling obtained by a competitor on comparable goods."
        ),
        "documents_available": (
            "Monthly Rule 42 workings, exempt turnover schedule, product "
            "specifications, the advance ruling relied on, supplier ledgers"
        ),
        "defects": [
            {"index": 1, "type": "itc_common_credit",
             "heading": "Rule 42 common credit reversal",
             "amount_by_head": heads(sgst=26000, cgst=26000)},
            {"index": 2, "type": "classification",
             "heading": "Classification and rate",
             "amount_by_head": heads(sgst=88000, cgst=88000)},
            {"index": 3, "type": "itc_180_days",
             "heading": "Rule 37 reversal",
             "amount_by_head": heads(sgst=9500, cgst=9500)},
        ],
    },
    expected={
        "position_taken": "partial",
        "position_keywords": ["Rule 42(2)", "advance ruling", "end use",
                              "re-availment"],
        "issues_expected": ["common credit", "classification", "Rule 37"],
        "procedural_points": ["65(6)", "personal hearing"],
        "must_not_say": ["the advance ruling binds this officer"],
        "outcome": (
            "Rule 42 limb reversed with interest at the audit stage. "
            "Classification carried to adjudication and decided in the "
            "taxpayer's favour on end-use evidence."
        ),
        "notes": (
            "An advance ruling obtained by another applicant does not bind "
            "this officer, and a reply that asserts otherwise loses "
            "credibility on the limb that matters most."
        ),
    },
    expected_defects=[
        {"index": 1, "posture": "agreed_paid",
         "required_evidence_that_was_missing": [
             "The annual Rule 42(2) reconciliation for the year, which was "
             "never prepared."]},
        {"index": 2, "posture": "contested",
         "required_evidence_that_was_missing": [
             "Product literature and end-use evidence for each commodity in "
             "the annexure."]},
        {"index": 3, "posture": "explained",
         "why": "Payment was made within time; the supplier ledger shows it."},
    ],
)


# ---------------------------------------------------------------------------
# 6. DRC-01B — Rule 88C. The matter that should be conceded.
# ---------------------------------------------------------------------------

DRC01B_TEXT = f"""GOVERNMENT OF HARYANA
EXCISE AND TAXATION DEPARTMENT
Office of the Deputy Excise and Taxation Commissioner (ST), Gurugram West

FORM GST DRC-01B
[See rule 88C]
Intimation of difference in liability reported in the statement of outward
supplies and that reported in the return

Reference No.: ZH060226220845N   Date: 16.02.2026

To
M/s. AARAV FASTENERS LIMITED
PLOT 19, SECTOR 34 INDUSTRIAL AREA, GURUGRAM - 122004

GSTIN: 06AAJCA6628R1ZK
Financial Year: 2024-25
Section under which notice is issued: 75
Date by which reply has to be submitted: 25.02.2026

• Difference in liability declared in GSTR-1 and that discharged in GSTR-3B:
The liability declared in your statement of outward supplies for the tax period
exceeds the liability discharged in the return for the same period. The
difference is as follows.
{row(sgst=21325, cgst=21325)}

You are required either to pay the differential liability with interest, or to
furnish an explanation for the difference, within the time stated above.

Signature
Name: N. K. AHLAWAT
Designation: Deputy Excise and Taxation Commissioner (ST)
Jurisdiction: Gurugram West , GURUGRAM , Haryana
"""

case(
    id="gst-drc01b-rule88c-liability",
    synthetic=True,
    provenance=(
        "Invented. Included because a golden set of matters that are all "
        "winnable trains the panel in the wrong direction: here the department "
        "is simply right, and the correct recommendation is to pay. No client "
        "matter involved."
    ),
    description=(
        "Rule 88C intimation on a single-period GSTR-1 versus GSTR-3B "
        "difference which is real, arithmetic, and should be paid."
    ),
    notice_text=DRC01B_TEXT,
    intake={
        "client_name": "AARAV FASTENERS LIMITED",
        "gstin": "06AAJCA6628R1ZK",
        "notice_type": "DRC-01B",
        "state": "Haryana",
        "tax_period": "FY 2024-25",
        "section_invoked": "75",
        "notice_date": "2026-02-16",
        "due_date": "2026-02-25",
        "amount_disputed": 42650,
        "facts": (
            "One invoice was reported in the statement of outward supplies but "
            "omitted from the return for the same month through a keying "
            "error. The omission is admitted and the tax has not been paid."
        ),
        "documents_available": (
            "GSTR-1 and GSTR-3B for the period, the invoice in question, "
            "electronic cash ledger"
        ),
        "defects": [
            {"index": 1, "type": "outward_short_payment",
             "heading": "Rule 88C difference in liability",
             "amount_by_head": heads(sgst=21325, cgst=21325)},
        ],
    },
    expected={
        "position_taken": "concede",
        "position_keywords": ["pay", "Rule 88C", "interest", "DRC-03"],
        "issues_expected": ["difference in liability"],
        "procedural_points": ["88C(1)", "Part B"],
        "must_not_say": ["contest the difference", "seek an adjournment"],
        "outcome": (
            "Paid with interest within the seven-day window. No further "
            "proceedings, and the return-filing block under Rule 59(6) never "
            "engaged."
        ),
        "notes": (
            "The value here is speed and a correct arithmetic check, not "
            "argument. A panel that convenes four counsel on this limb has "
            "cost the client more than the tax."
        ),
    },
    expected_defects=[
        {"index": 1, "posture": "agreed_paid",
         "why": "The difference is real and admitted. Pay it with interest "
                "before the Rule 59(6) filing block engages."},
    ],
)


# ---------------------------------------------------------------------------
# 7. REG-17 — cancellation. No figure at all: the product must report the
#    limb without inventing an amount for it.
# ---------------------------------------------------------------------------

REG17_TEXT = """GOVERNMENT OF UTTAR PRADESH
STATE TAX DEPARTMENT
Office of the Assistant Commissioner, Sector 62 Circle, Noida

FORM GST REG-17
[See rule 22(1)]
Notice for cancellation of registration

Reference No.: ZU090226741159C   Date: 02.02.2026

To
M/s. HARSHIT ENTERPRISES LIMITED
B-114, SECTOR 63, NOIDA - 201301

GSTIN: 09AAFCH2207N1ZB
Financial Year: 2025-26
Section under which notice is issued: 29
Date by which reply has to be submitted: 09.02.2026

• Cancellation of registration proposed for continuous non-filing of returns:
Returns have not been furnished by you for a continuous period of six months.
It appears that the registration is liable to be cancelled under Section
29(2)(c) read with Rule 22(1). You are called upon to show cause why the
registration should not be cancelled.

You may appear before the undersigned on the date stated above. Please note
that failure to reply will result in the matter being decided ex parte.

Signature
Name: A. K. TRIPATHI
Designation: Assistant Commissioner
Jurisdiction: Sector 62 Circle , NOIDA , Uttar Pradesh
"""

case(
    id="gst-reg17-cancellation",
    synthetic=True,
    provenance=(
        "Invented. Carries no head-wise figure anywhere, deliberately: the "
        "product must report this limb with an empty amount rather than "
        "attaching a number to it. No client matter involved."
    ),
    description=(
        "Cancellation notice for continuous non-filing — a limb with no "
        "quantification at all."
    ),
    notice_text=REG17_TEXT,
    intake={
        "client_name": "HARSHIT ENTERPRISES LIMITED",
        "gstin": "09AAFCH2207N1ZB",
        "notice_type": "REG-17",
        "state": "Uttar Pradesh",
        "tax_period": "FY 2025-26",
        "section_invoked": "29",
        "notice_date": "2026-02-02",
        "due_date": "2026-02-09",
        "facts": (
            "Business was suspended for two quarters following a fire at the "
            "principal place of business. The premises remain on rent and the "
            "insurance claim is on record. All pending returns can be filed "
            "with late fee before the hearing date."
        ),
        "documents_available": (
            "Rent agreement, utility bills, fire brigade report, insurance "
            "claim correspondence, bank statements, draft returns"
        ),
        "defects": [
            {"index": 1, "type": "registration",
             "heading": "Cancellation proposed for non-filing"},
        ],
    },
    expected={
        "position_taken": "explain",
        "position_keywords": ["Rule 22(4)", "returns filed", "existence of "
                              "business", "proportionality"],
        "issues_expected": ["cancellation for non-filing"],
        "procedural_points": ["29(2)(c)", "22(1)", "22(4)", "personal hearing"],
        "must_not_say": ["apply afresh for registration"],
        "outcome": (
            "All pending returns filed with late fee before the hearing; "
            "proceedings dropped under Rule 22(4)."
        ),
        "notes": (
            "No amount is in issue, and any figure attached to this limb is "
            "invented. The product must show the reviewer an empty amount."
        ),
    },
    expected_defects=[
        {"index": 1, "posture": "explained",
         "required_evidence_that_was_missing": [
             "Proof of existence and business activity at the principal place "
             "— rent agreement, utility bills and bank statements."]},
    ],
)


# ---------------------------------------------------------------------------
# 8. ASMT-13 — best judgment assessment
# ---------------------------------------------------------------------------

ASMT13_TEXT = f"""GOVERNMENT OF PUNJAB
DEPARTMENT OF EXCISE AND TAXATION
Office of the Excise and Taxation Officer, Ludhiana Division 3

FORM GST ASMT-13
[See rule 100(1)]
Assessment order under Section 62

Reference No.: ZP030226338674V   Date: 23.01.2026

To
M/s. GURPREET STEEL INDUSTRIES
FOCAL POINT PHASE V, LUDHIANA - 141010

GSTIN: 03AAKFG1174D1ZG
Financial Year: 2024-25
Section under which notice is issued: 62
Date by which reply has to be submitted: 22.02.2026

Whereas the return for the tax period stated above has not been furnished by
you despite notice, the liability has been assessed to the best of judgment on
the material available.

• Short payment of tax on outward supplies:
Outward supplies have been estimated on the basis of the e-way bills generated
on your portal login and the turnover declared in the immediately preceding
periods. The tax assessed is as follows.
{row(sgst=150000, cgst=150000)}

• Late fee for belated returns:
Late fee has been levied under Section 47 for the period of default. The amount
is as follows.
{row(sgst=5000, cgst=5000)}

This order shall be deemed to have been withdrawn if a valid return is
furnished within thirty days of service.

Signature
Name: J. S. GREWAL
Designation: Excise and Taxation Officer
Jurisdiction: Ludhiana Division 3 , LUDHIANA , Punjab
"""

case(
    id="gst-asmt13-best-judgment",
    synthetic=True,
    provenance=(
        "Invented. Written to cover the one form where the correct advice is "
        "procedural rather than substantive — file the return and the order "
        "falls away. No client matter involved."
    ),
    description=(
        "Best judgment assessment on an estimated turnover, withdrawable on "
        "filing a valid return within thirty days."
    ),
    notice_text=ASMT13_TEXT,
    intake={
        "client_name": "GURPREET STEEL INDUSTRIES",
        "gstin": "03AAKFG1174D1ZG",
        "notice_type": "ASMT-13",
        "state": "Punjab",
        "tax_period": "FY 2024-25",
        "section_invoked": "62",
        "notice_date": "2026-01-23",
        "due_date": "2026-02-22",
        "amount_disputed": 310000,
        "facts": (
            "Returns for two periods were not filed after the accountant left. "
            "Actual turnover for those periods is materially lower than the "
            "estimate, and the books support it."
        ),
        "documents_available": (
            "Sales register, e-way bill summary, purchase register, bank "
            "statements, draft returns ready for filing"
        ),
        "defects": [
            {"index": 1, "type": "outward_short_payment",
             "heading": "Estimated outward liability",
             "amount_by_head": heads(sgst=150000, cgst=150000)},
            {"index": 2, "type": "late_fee",
             "heading": "Late fee under Section 47",
             "amount_by_head": heads(sgst=5000, cgst=5000)},
        ],
    },
    expected={
        "position_taken": "explain",
        "position_keywords": ["Section 62(2)", "valid return", "thirty days",
                              "deemed withdrawn"],
        "issues_expected": ["estimated turnover", "late fee"],
        "procedural_points": ["62(2)", "100(1)", "thirty days"],
        "must_not_say": ["appeal the assessment order"],
        "outcome": (
            "Returns filed within thirty days; the order stood withdrawn "
            "under Section 62(2). Late fee and interest survived and were "
            "paid."
        ),
        "notes": (
            "Filing the return is the whole answer, and the thirty-day window "
            "is the only thing that matters. A panel that drafts grounds of "
            "appeal here has lost the matter by doing good work on the wrong "
            "question."
        ),
    },
    expected_defects=[
        {"index": 1, "posture": "explained",
         "required_evidence_that_was_missing": [
             "The valid return for each defaulted period, which is what causes "
             "the order to be withdrawn under Section 62(2)."]},
        {"index": 2, "posture": "agreed_paid",
         "why": "Late fee survives withdrawal of the assessment and is payable."},
    ],
)


# ---------------------------------------------------------------------------
# 9. MOV-07 — detention. The penalty is stated once and levied under two heads,
#    which read literally understates the exposure by half.
# ---------------------------------------------------------------------------

MOV07_TEXT = """GOVERNMENT OF WEST BENGAL
DIRECTORATE OF COMMERCIAL TAXES
Office of the Assistant Commissioner, Bureau of Investigation, Durgapur Range

FORM GST MOV-07
Notice under Section 129(3)

Reference No.: ZW190226485207D   Date: 06.02.2026

To
M/s. BENGAL CASTINGS LIMITED
NH-19 SERVICE ROAD, DURGAPUR - 713212

GSTIN: 19AADCB4416P1ZS
Financial Year: 2025-26
Section under which notice is issued: 129
Date by which reply has to be submitted: 13.02.2026

• E-way bill had expired at the time of interception:
The consignment intercepted on the date stated in the statement of the person
in charge was moving under an e-way bill whose validity had expired. Penalty of
Rs. 25,000/- each under CGST and SGST is accordingly proposed.

You are called upon to show cause why the proposed penalty should not be
imposed and the goods and conveyance released only on payment thereof.

Signature
Name: P. CHATTERJEE
Designation: Assistant Commissioner, Bureau of Investigation
Jurisdiction: Durgapur Range , DURGAPUR , West Bengal
"""

case(
    id="gst-mov07-eway-expired",
    synthetic=True,
    provenance=(
        "Invented. The penalty is deliberately stated as one figure levied "
        "under each of two heads, which is how these notices print it and "
        "which read literally understates the exposure by half. No client "
        "matter involved."
    ),
    description=(
        "Detention notice on an expired e-way bill where no intent to evade "
        "is alleged with particulars."
    ),
    notice_text=MOV07_TEXT,
    intake={
        "client_name": "BENGAL CASTINGS LIMITED",
        "gstin": "19AADCB4416P1ZS",
        "notice_type": "MOV-07",
        "state": "West Bengal",
        "tax_period": "FY 2025-26",
        "section_invoked": "129",
        "notice_date": "2026-02-06",
        "due_date": "2026-02-13",
        "amount_disputed": 50000,
        "facts": (
            "The vehicle broke down and was under repair for eleven hours, "
            "which is why validity lapsed. The invoice is reported in the "
            "outward statement for the month and the tax has been paid."
        ),
        "documents_available": (
            "Tax invoice, expired e-way bill, transporter breakdown "
            "certificate, repair bill, GSTR-1 extract for the month"
        ),
        "defects": [
            {"index": 1, "type": "eway_bill",
             "heading": "Expired e-way bill at interception",
             "amount_by_head": {"cgst": 25000.0, "sgst": 25000.0}},
        ],
    },
    expected={
        "position_taken": "contest",
        "position_keywords": ["no intent to evade", "expiry", "breakdown",
                              "Section 126"],
        "issues_expected": ["expired e-way bill", "penalty"],
        "procedural_points": ["129(3)", "126", "MOV-09"],
        "must_not_say": ["pay the penalty to obtain release and close the "
                         "matter"],
        "outcome": (
            "Penalty reduced to the general penalty on the finding that the "
            "lapse was procedural and the tax stood paid."
        ),
        "notes": (
            "The figure is stated once but levied twice. A reply that answers "
            "Rs. 25,000 has understated the client's exposure by half before "
            "it has argued anything."
        ),
    },
    expected_defects=[
        {"index": 1, "posture": "contested",
         "required_evidence_that_was_missing": [
             "The transporter's breakdown certificate and repair bill "
             "accounting for the hours by which validity lapsed."]},
    ],
)


# ---------------------------------------------------------------------------

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for entry in CASES:
        path = OUT / f"{entry['id']}.json"
        path.write_text(json.dumps(entry, indent=2, ensure_ascii=False) + "\n")
        print(f"wrote {path.name}")
    print(f"\n{len(CASES)} cases, "
          f"{len({c['intake']['notice_type'] for c in CASES})} distinct forms")


if __name__ == "__main__":
    main()

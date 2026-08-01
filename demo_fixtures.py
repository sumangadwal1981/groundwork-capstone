"""Replayable discoveries built from the raw-material pack.

The two KrishiCo fixtures are identical except for the answer to Q13. Coverage
is complete in both, so the readiness state flips on that one answer alone.
That is the demo.
"""
from groundwork import grading, playbook
from groundwork.models import Session

# Q13 withheld — supplied per variant below.
KRISHICO_BASE = [
    ("Q1", "I'm the founder of KrishiCo. We're an agri-inputs distributor working across "
           "twelve depots, mostly fertiliser and crop protection. Nine years in."),
    ("Q2", "I grew up in this trade. My father ran two of these depots and I spent every "
           "summer watching him guess at stock levels and get it wrong."),
    ("Q3", "I ran operations here for six years before taking over, so I've done the "
           "ordering myself at four of the twelve sites."),
    ("Q4", "Our depots either run out of stock or sit on it. We want demand forecasting "
           "across about 800 SKUs so we stop guessing."),
    ("Q5", "Depot managers feel it worst. They order on instinct and get blamed either way."),
    ("Q6", "Two bad seasons back to back. The write-offs got big enough that the board "
           "asked for a plan."),
    ("Q7", "Today it's a monthly gut call by each depot manager, sometimes with a "
           "spreadsheet they keep themselves."),
    ("Q8", "The input distribution market here is consolidating. The larger players "
           "already forecast centrally and we don't."),
    ("Q9", "Our competitors are two national distributors and a lot of small local "
           "traders. We win on relationships and depot coverage."),
    ("Q10", "Farmers and retail agri shops across twelve districts. We've sold to them "
            "for nine years and I can share the customer list export."),
    ("Q11", "What we know is the write-off number \u2014 I pulled that from our accounts "
            "myself. What we're assuming is that better forecasts would actually change "
            "ordering behaviour."),
    ("Q12", "Established business with real revenue \u2014 our finance head can send you "
            "the audited statements. This is a new capability, not a new company."),
    ("Q14", "We'd want a pilot at three depots before the next sowing season, then a "
            "rollout across all twelve over the following two quarters."),
    ("Q15", "There's me, a finance head, an ops head and twelve depot managers. No data "
            "team. We'd hire or partner for that."),
    ("Q16", "Funded from the business. Our finance head has allocated the budget and I "
            "can share the approval note."),
    ("Q17", "A working forecast that depot managers actually trust and use every week."),
    ("Q18", "A mid-size project, and we'd want it live before the next sowing season."),
]

Q13_ASPIRATIONAL = (
    "Q13", "Yes, we have an ERP with all the data in it. Everything we need is already "
           "in there, going back years.")

Q13_EVIDENCED = (
    "Q13", "We have an ERP, though honestly it's a custom Access database from 2014. "
           "Our ops head pulls the depot numbers each month and I can share the export "
           "so you can see what's actually in there.")

PAYWISE = [
    ("Q1", "I'm Aarav, founder of PayWise. I've been working on this for about eight months."),
    ("Q4", "Payments in this market are broken for small merchants. Fees, settlement "
           "delays, no visibility."),
    ("Q5", "Small merchants, the ones doing maybe a few lakh a month in volume."),
    ("Q6", "The timing is right because everyone's going digital and the AI piece is "
           "what makes us different."),
    ("Q7", "Right now they mostly use whatever their bank gives them, or cash."),
    ("Q8", "I think this is a huge market, honestly enormous. Everyone needs payments."),
    ("Q9", "There are incumbents but none of them are doing personalisation properly."),
    ("Q15", "It's me full time. A friend helps part-time on React Native. No technical "
            "co-founder yet, and no designer."),
    ("Q16", "Funding conversations are ongoing, nothing committed yet."),
]

FIXTURES = {
    "KrishiCo \u2014 the ERP claim, unevidenced": (
        "KrishiCo founder", "KrishiCo", KRISHICO_BASE + [Q13_ASPIRATIONAL]),
    "KrishiCo \u2014 same discovery, evidence supplied": (
        "KrishiCo founder", "KrishiCo (evidenced)", KRISHICO_BASE + [Q13_EVIDENCED]),
    "PayWise \u2014 the unqualified lead": ("Aarav", "PayWise", PAYWISE),
}


def load_fixture(name):
    founder, company, script = FIXTURES[name]
    s = Session(founder_name=founder, company=company)
    s.add_turn("agent", playbook.OPENING)
    for item_id, text in script:
        item = playbook.BY_ID[item_id]
        s.add_turn("agent", item.text)
        s.asked.append(item_id)
        claims, quarantined, _ = grading.grade_answer(s, item_id, text)
        if not quarantined:
            grading.update_coverage(s, item_id, text, claims)
    return s

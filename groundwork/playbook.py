"""The discovery playbook.

This is CONFIGURATION, not code. A different consultancy loads a different
playbook file and gets a different discovery instrument with no code changes
(PRD section 3, "Build vs Buy").

Versioned: a brief records which playbook version produced it, so any brief is
reproducible against the logic that generated it.
"""
from dataclasses import dataclass, field
from typing import Optional

PLAYBOOK_VERSION = "atliq-v3.1"

# The five claim topics that trigger the deterministic escalation rule.
# PRD FR-5. This is a RULE, not a model judgment: a claim on any of these
# topics requires an artifact or a named owner, or it stays unverified
# regardless of how confident the classifier is.
ESCALATION_TOPICS = {
    "systems_data": "Systems and data \u2014 existence, location, granularity, ownership, access",
    "traction": "Traction \u2014 revenue, users, pilots, retention, letters of intent",
    "team": "Team \u2014 roles that exist today versus intended hires",
    "funding": "Funding \u2014 committed versus in conversation",
    "regulatory": "Regulatory \u2014 licences held versus required",
}


@dataclass
class Item:
    id: str
    section: str
    text: str
    load_bearing: bool = False
    topic: Optional[str] = None          # escalation topic this item tends to elicit
    probes: list = field(default_factory=list)   # follow-ups when the answer is thin


ITEMS = [
    Item("Q1", "A. About you", "Your background, your current role, and your company if one exists yet."),
    Item("Q2", "A. About you",
         "How did you come to this problem? Why are you the right person to solve it?",
         probes=["What have you personally seen or lived that someone outside this problem would miss?"]),
    Item("Q3", "A. About you", "What have you done before this that prepares you to build it?"),

    Item("Q4", "B. Problem and idea", "In your own words, what is the pain point you are solving?"),
    Item("Q5", "B. Problem and idea", "Who feels this pain most acutely? Describe them as specifically as you can."),
    Item("Q6", "B. Problem and idea", "What triggered this idea now? Why is this the right moment?"),
    Item("Q7", "B. Problem and idea", "What do these people do today instead \u2014 workarounds, tools, or living with it?"),

    Item("Q8", "C. Market", "How do you see the market for this idea, and which way is it moving?"),
    Item("Q9", "C. Market", "Who are your competitors or closest alternatives, and how will you be different?"),
    Item("Q10", "C. Market", "Who exactly is your target customer \u2014 segment, geography, willingness to pay?",
         load_bearing=True,
         probes=["If you had to pick ONE segment to launch into, which and why?"]),
    Item("Q11", "C. Market", "Of everything above, what do you know from evidence and what are you still assuming?",
         topic="traction"),

    Item("Q12", "D. Stage and plans", "What stage is the business at \u2014 idea, MVP, early revenue, growing?",
         load_bearing=True, topic="traction"),
    Item("Q13", "D. Stage and plans",
         "What have you already built or tried? Do you have existing systems or data related to the idea, "
         "even spreadsheets?",
         load_bearing=True, topic="systems_data",
         probes=["Who actually pulls that data today, and how often?",
                 "What granularity does it hold \u2014 daily, weekly, monthly?",
                 "Could you share a screenshot or an export of it?"]),
    Item("Q14", "D. Stage and plans", "What is your launch plan and timeline for the next 6\u201312 months?"),
    Item("Q15", "D. Stage and plans", "Who is on the team today? Are you looking to hire?",
         topic="team"),
    Item("Q16", "D. Stage and plans", "How is this funded \u2014 bootstrapped or raising? What is committed versus in conversation?",
         load_bearing=True, topic="funding"),

    Item("Q17", "E. Working with AtliQ", "What would a great outcome from an engagement with AtliQ look like?",
         load_bearing=True),
    Item("Q18", "E. Working with AtliQ", "What budget range are you working with, and are there hard deadlines?",
         load_bearing=True),
]

BY_ID = {i.id: i for i in ITEMS}
LOAD_BEARING = [i.id for i in ITEMS if i.load_bearing]

# Regulatory is not tied to a single question. It is a topic that can surface
# anywhere, which is exactly what caught PayWise: nobody asked about PA/PG
# licensing, and the founder had not considered it.
LATENT_TOPICS = ["regulatory"]

OPENING = (
    "I'm here to understand your idea properly before you spend time on a call with Bhavin. "
    "There's no form and no right order \u2014 talk about whatever's most alive for you, and I'll "
    "keep track of what we've covered. You can stop and come back whenever you like.\n\n"
    "So: what are you building, and what's the problem underneath it?"
)

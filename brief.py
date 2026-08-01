"""Coverage arithmetic, the readiness signal, and brief assembly.

Thresholds are PRD section 5A. They are constants here rather than magic
numbers scattered through the code, because they are product decisions and
should be visible and changeable.
"""
import re

from . import llm, playbook
from .models import (COVERED, PARTIAL, NOT_DISCUSSED, UNVERIFIED,
                     SCOPE_READY, BRIEF_PARTIAL, INSUFFICIENT)

SCOPE_READY_COVERAGE = 0.85
PARTIAL_COVERAGE = 0.60


def coverage_pct(session):
    total = len(playbook.ITEMS)
    hit = sum(1 for s in session.coverage.values() if s in (COVERED, PARTIAL))
    return hit / total if total else 0.0


def load_bearing_gaps(session):
    return [i for i in playbook.LOAD_BEARING if session.coverage.get(i) != COVERED]


def unverified_load_bearing(session):
    return [c for c in session.claims if c.load_bearing and c.grade == UNVERIFIED]


def readiness(session):
    """Returns (state, reasons).

    INSUFFICIENT if coverage < 60%, OR any load-bearing item not covered,
    OR any load-bearing claim unverified. Below threshold emits NO shape
    recommendation at all - it does not degrade to a weaker one.
    """
    pct = coverage_pct(session)
    gaps = load_bearing_gaps(session)
    unver = unverified_load_bearing(session)
    reasons = []

    if pct < PARTIAL_COVERAGE:
        reasons.append(f"Playbook coverage is {pct:.0%}, below the {PARTIAL_COVERAGE:.0%} floor.")
    for g in gaps:
        reasons.append(f"Load-bearing item {g} is not covered \u2014 {playbook.BY_ID[g].text[:70]}")
    for c in unver:
        reasons.append(f"Load-bearing claim on {c.item_id} is unverified \u2014 \u201c{c.text[:80]}\u201d")

    if pct < PARTIAL_COVERAGE or gaps or unver:
        return INSUFFICIENT, reasons
    if pct < SCOPE_READY_COVERAGE:
        return BRIEF_PARTIAL, [f"Coverage is {pct:.0%}; all load-bearing items are covered and evidenced."]
    return SCOPE_READY, [f"Coverage is {pct:.0%}; all load-bearing items covered and evidenced."]


def recommend_shape(session):
    """Engagement shape. Emitted ONLY when readiness is not INSUFFICIENT.

    This is evidence for Bhavin's decision, never the decision. It never
    reaches the founder.
    """
    state, reasons = readiness(session)
    if state == INSUFFICIENT:
        return None, reasons

    by_item = {c.item_id: c for c in session.claims}
    stage = (by_item.get("Q12").text if by_item.get("Q12") else "")
    funding = (by_item.get("Q16").text if by_item.get("Q16") else "")
    systems = by_item.get("Q13")

    def has(text, *phrases):
        """Word-boundary match. Substring matching gave false positives:
        'no' fired inside 'note', which flipped a build into an advisory sprint."""
        return any(re.search(r"\b" + re.escape(p) + r"\b", text, re.I) for p in phrases)

    early = has(stage, "idea", "concept", "pre-revenue", "prototype", "mvp", "nothing yet")
    thin_money = has(funding, "bootstrapped", "not committed", "nothing committed",
                     "ongoing", "in conversation", "no funding", "raising")
    no_data = systems is not None and systems.grade == UNVERIFIED

    if early or thin_money:
        shape = "Advisory sprint"
        why = ("Stage and funding evidence point to shaping work rather than a build. "
               "A short advisory engagement de-risks scope before either side commits.")
    elif no_data:
        shape = "Data audit, then build"
        why = "The build depends on data whose shape is not yet established. Audit first."
    else:
        shape = "Build engagement"
        why = "Stage, funding and systems evidence support scoping a build."
    return {"shape": shape, "why": why}, reasons


def assemble(session):
    """The consultant-facing discovery brief."""
    from .grading import outstanding

    missing = [playbook.BY_ID[i].text[:50]
               for i, s in session.coverage.items() if s == NOT_DISCUSSED]
    narrative = llm.write_brief(session, session.claims, missing)
    state, reasons = readiness(session)
    rec, _ = recommend_shape(session)

    return {
        "playbook_version": session.playbook_version,
        "coverage_pct": coverage_pct(session),
        "coverage": dict(session.coverage),
        "state": session.signal_override or state,
        "state_overridden": bool(session.signal_override),
        "reasons": reasons,
        "recommendation": rec,
        "claims": session.claims,
        "outstanding": outstanding(session),
        "narrative": narrative,
        "quarantined": [t for t in session.turns if t.quarantined],
    }

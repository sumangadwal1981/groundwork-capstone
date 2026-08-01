"""Claim grading and the escalation rule.

The escalation rule is the one piece of this system that does not trust the
model. It is a deterministic check that fires on topic alone, regardless of how
confident the classifier was. That is the design decision that would have
caught KrishiCo (PRD FR-5, section 6).
"""
import re
import uuid

from . import llm, playbook, safety
from .models import (Claim, COVERED, PARTIAL, NOT_DISCUSSED,
                     EVIDENCE_BACKED, ASSUMED, UNVERIFIED)

# Evidence that satisfies the escalation rule: an artifact, or a named person
# who actually touches the thing.
_ARTIFACT_CUES = ["screenshot", "export", "csv", "attached", "i can share",
                  "sending you", "here is the", "schema", "sample file", "dump"]
_OWNER_PATTERNS = [
    re.compile(r"\b(?:our|the|my)\s+(ops head|operations head|cto|data lead|"
               r"analyst|finance head|it manager|admin|depot manager|head of \w+)\b", re.I),
    re.compile(r"\b([A-Z][a-z]+)\s+(?:handles|owns|pulls|maintains|manages)\b"),
]


def detect_evidence(text):
    """Look for an artifact or a named data owner in the founder's own words."""
    low = (text or "").lower()
    artifact = next((c for c in _ARTIFACT_CUES if c in low), None)
    owner = None
    for pat in _OWNER_PATTERNS:
        m = pat.search(text or "")
        if m:
            owner = m.group(1)
            break
    return artifact, owner


def apply_escalation(claim: Claim) -> Claim:
    """THE HARD RULE.

    A claim on any escalation topic requires an artifact or a named owner.
    Absent either, it is held as unverified no matter what the classifier said.
    This runs after the model, and the model cannot talk it out of firing.
    """
    if claim.topic not in playbook.ESCALATION_TOPICS:
        return claim
    if claim.artifact or claim.named_owner:
        return claim
    claim.escalated = True
    if claim.grade != UNVERIFIED:
        claim.note = (f"Escalation rule fired on topic '{claim.topic}': no artifact and no named "
                      f"owner supplied, so the model's grade of '{claim.grade}' was overruled.")
        claim.grade = UNVERIFIED
    else:
        claim.note = f"Escalation rule fired on topic '{claim.topic}': evidence still outstanding."
    return claim


def grade_answer(session, item_id, raw_text):
    """Screen, strip, extract, grade, escalate. Returns (claims, quarantined, removed)."""
    adversarial, reason = safety.screen(raw_text)
    if adversarial:
        session.add_turn("founder", raw_text, quarantined=True, reason=reason)
        session.log("quarantine", {"reason": reason, "turn": len(session.turns) - 1})
        return [], True, []

    clean, removed = safety.strip_excluded(raw_text)
    if removed:
        session.log("excluded_attribute", {"removed": removed})
    turn = session.add_turn("founder", raw_text)

    artifact, owner = detect_evidence(clean)
    out = []
    for raw in llm.extract_claims(clean, item_id):
        grade = raw.get("grade") or ASSUMED
        if grade not in (EVIDENCE_BACKED, ASSUMED, UNVERIFIED):
            grade = UNVERIFIED                     # low confidence resolves DOWN
        c = Claim(
            id=uuid.uuid4().hex[:8],
            text=(raw.get("text") or clean)[:400],
            item_id=item_id,
            topic=raw.get("topic"),
            grade=grade,
            model_grade=grade,
            citation_turn=turn.idx,
            artifact=artifact,
            named_owner=owner,
        )
        out.append(apply_escalation(c))

    session.claims.extend(out)
    session.log("graded", {"item": item_id, "claims": len(out),
                           "escalated": sum(1 for c in out if c.escalated)})
    return out, False, removed


def update_coverage(session, item_id, raw_text, claims):
    """An item is covered when it drew at least one claim and a real answer.

    Thin answers mark the item partial, which keeps it eligible for a probe
    without re-asking it from scratch.
    """
    if not item_id:
        return
    words = len((raw_text or "").split())
    item = playbook.BY_ID.get(item_id)
    escalated_open = any(c.escalated and not (c.artifact or c.named_owner) for c in claims)

    if words < 8:
        # Barely an answer at all.
        state = PARTIAL if words else NOT_DISCUSSED
    elif not claims:
        # A real answer that produced no gradeable claim. This is normal for
        # items that ask about intent rather than fact - "what would a great
        # outcome look like", "what is your launch plan". The founder answered;
        # there is simply nothing here to grade. Treat it as covered, or the
        # brief reports items as never discussed when they plainly were.
        state = COVERED
    elif escalated_open and item and item.load_bearing:
        # The founder answered, but a load-bearing claim is still unevidenced.
        # Covered as a conversation, not as evidence: the readiness check is
        # what stops this reaching scope-ready.
        state = COVERED
    else:
        state = COVERED

    prior = session.coverage.get(item_id, NOT_DISCUSSED)
    if prior == COVERED and state == PARTIAL:
        return
    session.coverage[item_id] = state


def outstanding(session):
    """What Bhavin still has to chase, in the order it matters."""
    items = []
    for c in session.claims:
        if c.grade == UNVERIFIED and c.escalated:
            it = playbook.BY_ID.get(c.item_id)
            label = f"{c.item_id} \u00b7 {it.text[:60]}" if it else (c.topic or "claim")
            items.append({
                "kind": "evidence",
                "priority": 1 if c.load_bearing else 2,
                "text": f"{label} \u2014 needs an artifact or the person who owns it",
                "claim": c.text,
                "topic": c.topic,
            })
    for iid, state in session.coverage.items():
        if state == NOT_DISCUSSED:
            it = playbook.BY_ID[iid]
            items.append({
                "kind": "coverage",
                "priority": 1 if it.load_bearing else 3,
                "text": f"{iid} \u00b7 {it.text[:60]} \u2014 never discussed",
                "claim": "", "topic": it.topic,
            })
    return sorted(items, key=lambda x: x["priority"])

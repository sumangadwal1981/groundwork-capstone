"""Model adapter.

The PRD names capabilities, not models (section 3), so the rest of the codebase
talks to this interface and never to a vendor SDK. Swapping models is a config
change.

Two modes:
  live  - calls a hosted model API. Needs ANTHROPIC_API_KEY.
  stub  - deterministic rule-based responses. No network, no key. Used by the
          test suite and available in the UI so the prototype can be
          demonstrated without credentials.

Set GROUNDWORK_LLM_MODE=live|stub (default: stub if no key is present).
"""
import json
import os
import re

from . import playbook

MODEL_STRONG = os.environ.get("GROUNDWORK_MODEL_STRONG", "claude-sonnet-4-6")
MODEL_SMALL = os.environ.get("GROUNDWORK_MODEL_SMALL", "claude-haiku-4-5-20251001")


def mode():
    m = os.environ.get("GROUNDWORK_LLM_MODE")
    if m:
        return m
    return "live" if os.environ.get("ANTHROPIC_API_KEY") else "stub"


# ---------------------------------------------------------------- live -----
def _call(model, system, user, max_tokens=1200):
    import anthropic
    client = anthropic.Anthropic()
    r = client.messages.create(
        model=model, max_tokens=max_tokens, system=system,
        messages=[{"role": "user", "content": user}],
    )
    return "".join(b.text for b in r.content if b.type == "text")


def _json(raw, fallback):
    raw = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.M).strip()
    try:
        return json.loads(raw)
    except Exception:
        m = re.search(r"[\{\[].*[\}\]]", raw, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                pass
    return fallback


# ------------------------------------------------------------ questions ----
NEXT_Q_SYSTEM = """You run intake for a consulting practice. You are interviewing a founder.

Rules you never break:
- Ask ONE question. Never more.
- You may only ask about items in the playbook you are given. Do not invent topics.
- Never assert a fact about the founder's business. You ask; you do not tell.
- Never give advice, opinions, or encouragement about the idea itself.
- Acknowledge what they just said in at most one short clause, then ask.
- Plain language. No consultant jargon. Never number your question.

Return JSON only: {"item_id": "<playbook id>", "question": "<what you say>"}"""


def next_question(session, remaining_items, last_answer):
    if mode() == "stub":
        return _stub_next_question(remaining_items, last_answer)
    lines = [f"{i.id} [{i.section}] {i.text}" for i in remaining_items]
    recent = "\n".join(f"{t.role}: {t.text}" for t in session.turns[-6:])
    user = (f"PLAYBOOK ITEMS STILL OPEN:\n" + "\n".join(lines) +
            f"\n\nRECENT CONVERSATION:\n{recent}\n\n"
            "Pick the item that follows most naturally from what they just said. "
            "If their last answer was thin on an item you already asked, ask a probe instead.")
    out = _json(_call(MODEL_SMALL, NEXT_Q_SYSTEM, user, 400), None)
    if not out or "question" not in out:
        return _stub_next_question(remaining_items, last_answer)
    return out.get("item_id") or (remaining_items[0].id if remaining_items else None), out["question"]


def _stub_next_question(remaining_items, last_answer):
    if not remaining_items:
        return None, "That's everything I needed. Thanks \u2014 I'll put this in front of Bhavin."
    nxt = remaining_items[0]
    lead = "Got it. " if last_answer else ""
    return nxt.id, lead + nxt.text


# --------------------------------------------------------------- claims ----
EXTRACT_SYSTEM = """Extract material claims from a founder's answer.

A claim is MATERIAL when both hold:
  (a) it asserts a fact about the world, not an intention or an opinion, AND
  (b) a consulting proposal would need rework if it turned out to be false.

Intentions ("we plan to launch in Q1") are NOT claims. Opinions are claims only
where an evidence basis is asserted.

For each claim assign:
  topic  - one of systems_data, traction, team, funding, regulatory, or null
  grade  - evidence_backed (they cited data, a document, a number they have seen)
         - assumed (they believe it, no evidence offered)
         - unverified (vague, second-hand, or contradicts something earlier)

Grade on evidence only. Never grade on who the founder is, how impressive they
sound, or how confident they seem. If uncertain, grade DOWN to unverified.
Never grade a claim as false; only as un-evidenced.

Return JSON only:
{"claims":[{"text":"...","topic":"systems_data"|null,"grade":"assumed"}]}"""


def extract_claims(answer_text, item_id):
    if mode() == "stub":
        return _stub_extract(answer_text, item_id)
    user = f"PLAYBOOK ITEM BEING ANSWERED: {item_id}\n\nFOUNDER SAID:\n{answer_text}"
    out = _json(_call(MODEL_STRONG, EXTRACT_SYSTEM, user, 900), {"claims": []})
    return out.get("claims", [])


# Keyword surfaces for the offline stub. Crude on purpose: the point of the
# stub is to exercise the state machine and the deterministic rule, not to
# simulate a classifier.
_TOPIC_CUES = {
    "systems_data": ["erp", "database", "spreadsheet", "excel", "data", "system",
                     "crm", "records", "history", "warehouse", "sql", "access"],
    "traction": ["revenue", "users", "customers", "pilot", "retention", "paying",
                 "signed", "loi", "waitlist", "traction", "mrr", "arr"],
    "team": ["co-founder", "cofounder", "team", "hire", "engineer", "designer",
             "developer", "part-time", "friend"],
    "funding": ["raising", "funded", "bootstrapped", "investor", "committed",
                "seed", "angel", "runway", "budget"],
    "regulatory": ["licence", "license", "kyc", "regulat", "compliance", "rbi",
                   "gdpr", "audit", "legal"],
}
_EVIDENCE_CUES = ["screenshot", "export", "attached", "i pulled", "our dashboard",
                  "last month we", "the report shows", "i can share", "csv"]
_HEDGE_CUES = ["i think", "probably", "should be", "i believe", "pretty sure",
               "we assume", "ongoing", "in conversation", "not yet", "roughly"]


def _stub_extract(answer_text, item_id):
    text = answer_text.strip()
    if not text:
        return []
    low = text.lower()
    topic = None
    for t, cues in _TOPIC_CUES.items():
        if any(c in low for c in cues):
            topic = t
            break
    if any(c in low for c in _EVIDENCE_CUES):
        grade = "evidence_backed"
    elif any(c in low for c in _HEDGE_CUES):
        grade = "unverified"
    else:
        grade = "assumed"
    sentences = [s.strip() for s in re.split(r"[.;\n]", text) if len(s.strip()) > 25]
    claim_text = sentences[0] if sentences else text[:180]
    return [{"text": claim_text, "topic": topic, "grade": grade}]


# ---------------------------------------------------------------- brief ----
BRIEF_SYSTEM = """Write a discovery brief for a consultant from a founder intake.

Absolute rules:
- Every sentence must be traceable to a numbered turn you were given. Cite as [t12].
- If something was not discussed, say so. Never infer it, never fill it in from
  context, never carry it over from a similar engagement.
- Do not evaluate the founder as a person. Report claims, not impressions.
- Do not recommend an engagement shape here. That is computed separately.

Return JSON only:
{"summary":"2-3 sentences, each with a [tN] citation",
 "contradictions":["..."],
 "not_discussed_note":"one sentence"}"""


def write_brief(session, claims, missing_labels):
    if mode() == "stub":
        return _stub_brief(session, claims, missing_labels)
    turns = "\n".join(f"[t{t.idx}] {t.role}: {t.text}"
                      for t in session.turns if not t.quarantined)
    cl = "\n".join(f"- {c.text} ({c.grade}, from [t{c.citation_turn}])" for c in claims)
    user = (f"TURNS:\n{turns}\n\nGRADED CLAIMS:\n{cl}\n\n"
            f"NEVER DISCUSSED: {', '.join(missing_labels) or 'nothing'}")
    return _json(_call(MODEL_STRONG, BRIEF_SYSTEM, user, 1400),
                 _stub_brief(session, claims, missing_labels))


def _stub_brief(session, claims, missing_labels):
    backed = [c for c in claims if c.grade == "evidence_backed"]
    unver = [c for c in claims if c.grade == "unverified"]
    bits = []
    if backed:
        bits.append(f"{backed[0].text} [t{backed[0].citation_turn}]")
    if unver:
        bits.append(f"Held as unverified: {unver[0].text} [t{unver[0].citation_turn}]")
    if not bits:
        bits.append("No material claims were established in this conversation.")
    return {
        "summary": " ".join(bits),
        "contradictions": [],
        "not_discussed_note": (
            f"Never discussed: {', '.join(missing_labels)}." if missing_labels
            else "Every playbook item was touched."),
    }

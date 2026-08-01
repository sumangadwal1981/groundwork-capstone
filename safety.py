"""Guardrails that do not depend on the model behaving.

PRD section 6. All founder input is data, never instruction. Anything that
reads as an instruction to the system is quarantined: excluded from grading
and synthesis context, flagged to the consultant with the raw text preserved,
and the conversation carries on without acting on it.
"""
import re

_INJECTION_PATTERNS = [
    r"\bignore (?:all |any |the )?(?:previous|prior|above|earlier)\b",
    r"\bdisregard (?:all |any |the )?(?:previous|prior|above|earlier)\b",
    r"\byou are (?:now )?(?:a|an|acting as)\b",
    r"\bnew instructions?\b",
    r"\bsystem prompt\b",
    r"\bmark (?:this|it|everything|all) as (?:evidence|verified|scope)",
    r"\bgrade (?:this|it|everything|all) as\b",
    r"\bset (?:the )?(?:readiness|signal|status) to\b",
    r"\boverride\b.{0,24}\b(?:grade|signal|threshold)\b",
    r"\bpretend\b.{0,30}\b(?:you|the system)\b",
    r"</?(?:system|instruction|prompt)>",
    r"\bskip (?:the )?(?:escalation|verification|check)\b",
]

_COMPILED = [re.compile(p, re.I) for p in _INJECTION_PATTERNS]


def screen(text):
    """Return (is_adversarial, reason)."""
    for p in _COMPILED:
        m = p.search(text or "")
        if m:
            return True, f"instruction-shaped content matched: {m.group(0)[:60]!r}"
    return False, ""


# ---------------------------------------------------------------------------
# Deliberately excluded from context (PRD section 4B). These are stripped
# before any text reaches the model, so exclusion is structural rather than a
# polite request in a prompt.
_EXCLUDE_PATTERNS = [
    (re.compile(r"\b(?:I am|I'm|he is|she is|they are)\s+\d{1,2}\s+years?\s+old\b", re.I), "[age withheld]"),
    (re.compile(r"\b(?:graduated from|alum(?:nus|na) of|studied at)\s+[A-Z][\w'\-]+(?:\s+[A-Z][\w'\-]+)*", re.I),
     "[education withheld]"),
    (re.compile(r"\bex-(?:google|meta|amazon|microsoft|mckinsey|bain|bcg|goldman)\b", re.I),
     "[prior employer withheld]"),
]


def strip_excluded(text):
    """Remove attributes that must not influence grading. Returns (clean, removed)."""
    removed = []
    out = text or ""
    for pat, repl in _EXCLUDE_PATTERNS:
        if pat.search(out):
            removed.append(repl)
            out = pat.sub(repl, out)
    return out, removed

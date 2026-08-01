"""Data model for a discovery session."""
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional
import uuid

from . import playbook

NOT_DISCUSSED = "not_discussed"
PARTIAL = "partial"
COVERED = "covered"

EVIDENCE_BACKED = "evidence_backed"
ASSUMED = "assumed"
UNVERIFIED = "unverified"

GRADE_LABEL = {
    EVIDENCE_BACKED: "Evidence-backed",
    ASSUMED: "Assumed",
    UNVERIFIED: "Unverified",
}

SCOPE_READY = "scope_ready"
BRIEF_PARTIAL = "partial"
INSUFFICIENT = "insufficient"


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Turn:
    idx: int
    role: str                      # "agent" | "founder"
    text: str
    sitting: int = 1
    quarantined: bool = False
    quarantine_reason: str = ""
    at: str = field(default_factory=_now)


@dataclass
class Claim:
    id: str
    text: str                      # the claim, in the founder's own terms
    item_id: Optional[str]         # playbook item it answers, if any
    topic: Optional[str]           # escalation topic, if any
    grade: str
    citation_turn: int             # index of the founder turn it came from
    model_grade: Optional[str] = None   # what the classifier said before the rule
    escalated: bool = False
    artifact: Optional[str] = None
    named_owner: Optional[str] = None
    note: str = ""
    overridden_by: Optional[str] = None
    override_from: Optional[str] = None
    at: str = field(default_factory=_now)

    @property
    def load_bearing(self) -> bool:
        return self.item_id in playbook.LOAD_BEARING


@dataclass
class Session:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    founder_name: str = ""
    company: str = ""
    playbook_version: str = playbook.PLAYBOOK_VERSION
    sitting: int = 1
    turns: list = field(default_factory=list)
    claims: list = field(default_factory=list)
    coverage: dict = field(default_factory=lambda: {i.id: NOT_DISCUSSED for i in playbook.ITEMS})
    asked: list = field(default_factory=list)          # item ids already asked
    audit: list = field(default_factory=list)
    signal_override: Optional[str] = None
    created_at: str = field(default_factory=_now)

    # ---- convenience -------------------------------------------------
    def add_turn(self, role, text, quarantined=False, reason=""):
        t = Turn(idx=len(self.turns), role=role, text=text, sitting=self.sitting,
                 quarantined=quarantined, quarantine_reason=reason)
        self.turns.append(t)
        return t

    def founder_turns(self):
        return [t for t in self.turns if t.role == "founder" and not t.quarantined]

    def log(self, event, detail):
        self.audit.append({"at": _now(), "event": event, "detail": detail})

    def to_dict(self):
        d = asdict(self)
        return d

    @classmethod
    def from_dict(cls, d):
        s = cls(**{k: v for k, v in d.items() if k not in ("turns", "claims")})
        s.turns = [Turn(**t) for t in d.get("turns", [])]
        s.claims = [Claim(**c) for c in d.get("claims", [])]
        return s

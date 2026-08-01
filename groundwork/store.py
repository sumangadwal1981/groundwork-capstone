"""Session persistence.

FR-1 requires a founder to leave and resume without losing state or repeating
answers. A JSON file store is sufficient at AtliQ's volume (~30 discoveries a
month) and keeps the prototype dependency-free. Swap for Postgres when
multi-tenant (PRD section 9, deferred).
"""
import json
import os
from pathlib import Path

from .models import Session

DATA_DIR = Path(os.environ.get("GROUNDWORK_DATA", "./data"))


def _path(session_id):
    return DATA_DIR / f"{session_id}.json"


def save(session: Session):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = _path(session.id).with_suffix(".tmp")
    tmp.write_text(json.dumps(session.to_dict(), indent=2), encoding="utf-8")
    tmp.replace(_path(session.id))       # atomic: a turn is never half-written
    return session.id


def load(session_id):
    p = _path(session_id)
    if not p.exists():
        return None
    return Session.from_dict(json.loads(p.read_text(encoding="utf-8")))


def list_sessions():
    if not DATA_DIR.exists():
        return []
    out = []
    for p in sorted(DATA_DIR.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            out.append({"id": d["id"], "founder": d.get("founder_name") or "(unnamed)",
                        "company": d.get("company") or "", "turns": len(d.get("turns", [])),
                        "created": d.get("created_at", "")})
        except Exception:
            continue
    return out

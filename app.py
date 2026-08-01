"""Groundwork — adaptive discovery agent.

Two surfaces:
  Founder    - the conversation. Never shows a grade or a readiness signal.
  Consultant - the brief. Grades, escalations, outstanding items, and the
               readiness signal, with override.

The separation is a guardrail, not a layout choice (PRD section 6).
"""
import os
import sys

import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from groundwork import brief as briefmod            # noqa: E402
from groundwork import grading, llm, playbook, store  # noqa: E402
from groundwork.models import (Session, COVERED, PARTIAL, NOT_DISCUSSED,   # noqa: E402
                               EVIDENCE_BACKED, ASSUMED, UNVERIFIED,
                               GRADE_LABEL, SCOPE_READY, BRIEF_PARTIAL, INSUFFICIENT)
from demo_fixtures import FIXTURES, load_fixture     # noqa: E402

st.set_page_config(page_title="Groundwork", page_icon="\u25e7", layout="wide")

GRADE_COLOR = {EVIDENCE_BACKED: "#2F6B4F", ASSUMED: "#9A6B1F", UNVERIFIED: "#A33A3A"}
STATE_COLOR = {SCOPE_READY: "#2F6B4F", BRIEF_PARTIAL: "#9A6B1F", INSUFFICIENT: "#A33A3A"}
STATE_LABEL = {SCOPE_READY: "Scope-ready", BRIEF_PARTIAL: "Partial",
               INSUFFICIENT: "Insufficient for scoping"}

st.markdown("""
<style>
  .chip{display:inline-block;padding:2px 9px;border-radius:2px;font-size:11px;
        font-weight:600;letter-spacing:.04em;text-transform:uppercase;color:#fff}
  .cite{color:#7A7A72;font-size:12px;font-family:ui-monospace,monospace}
  .claim{border-left:3px solid #D9D7CE;padding:8px 0 8px 14px;margin-bottom:14px}
  .rule{background:#FBEDED;border-left:3px solid #A33A3A;padding:10px 14px;
        font-size:13px;margin-top:6px}
  .absent{border:1px dashed #A33A3A;padding:18px;text-align:center;color:#A33A3A;
          font-size:14px;line-height:1.5}
  .lbl{font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:#7A7A72;
       font-weight:600;margin-bottom:4px}
</style>""", unsafe_allow_html=True)


# ----------------------------------------------------------------- state --
def current():
    return st.session_state.get("session")


def persist():
    if current():
        store.save(current())


def start(founder="", company=""):
    s = Session(founder_name=founder, company=company)
    s.add_turn("agent", playbook.OPENING)
    st.session_state.session = s
    store.save(s)


# ---------------------------------------------------------------- sidebar --
with st.sidebar:
    st.markdown("### Groundwork")
    st.caption(f"playbook `{playbook.PLAYBOOK_VERSION}` \u00b7 model mode `{llm.mode()}`")
    if llm.mode() == "stub":
        st.info("Running without an API key. Question selection and grading use "
                "deterministic stubs; the escalation rule, thresholds and guardrails "
                "are the real ones.", icon="\u2139\ufe0f")

    view = st.radio("Surface", ["Founder", "Consultant"], horizontal=True,
                    label_visibility="collapsed")
    st.divider()

    st.markdown('<div class="lbl">Load a discovery</div>', unsafe_allow_html=True)
    fx = st.selectbox("Replay", ["\u2014"] + list(FIXTURES), label_visibility="collapsed")
    if st.button("Replay this discovery", use_container_width=True, disabled=(fx == "\u2014")):
        st.session_state.session = load_fixture(fx)
        persist()
        st.rerun()

    with st.expander("New discovery"):
        f = st.text_input("Founder")
        c = st.text_input("Company")
        if st.button("Start", use_container_width=True):
            start(f, c)
            st.rerun()

    saved = store.list_sessions()
    if saved:
        with st.expander(f"Resume ({len(saved)})"):
            for row in saved[:12]:
                if st.button(f"{row['company'] or row['founder']} \u00b7 {row['turns']} turns",
                             key=f"r{row['id']}", use_container_width=True):
                    st.session_state.session = store.load(row["id"])
                    st.rerun()

if not current():
    start()

s = current()

# =========================================================== FOUNDER VIEW ==
if view == "Founder":
    st.markdown("#### Tell us about your idea")
    st.caption("No form, no order. Stop and come back whenever you like \u2014 "
               "we'll pick up where you left off.")

    for t in s.turns:
        if t.quarantined:
            continue
        with st.chat_message("assistant" if t.role == "agent" else "user"):
            st.write(t.text)

    if msg := st.chat_input("Type your answer\u2026"):
        item_id = s.asked[-1] if s.asked else None
        claims, quarantined, removed = grading.grade_answer(s, item_id, msg)
        if quarantined:
            with st.chat_message("assistant"):
                st.write("Let's stay with your business \u2014 could you tell me more about "
                         "the last point in your own words?")
            s.add_turn("agent", "Let's stay with your business.")
        else:
            grading.update_coverage(s, item_id, msg, claims)
            open_claims = [c for c in claims if c.escalated]
            remaining = [i for i in playbook.ITEMS
                         if s.coverage.get(i.id) == NOT_DISCUSSED and i.id not in s.asked]
            if open_claims and open_claims[0].item_id:
                item = playbook.BY_ID.get(open_claims[0].item_id)
                probe = (item.probes[0] if item and item.probes
                         else "Could you share something that shows that \u2014 an export, a "
                              "screenshot, or the name of whoever handles it day to day?")
                s.add_turn("agent", probe)
            else:
                nid, q = llm.next_question(s, remaining, msg)
                if nid:
                    s.asked.append(nid)
                s.add_turn("agent", q)
        persist()
        st.rerun()

    pct = briefmod.coverage_pct(s)
    st.divider()
    st.progress(pct, text=f"We've covered {pct:.0%} of what Bhavin needs")
    st.caption("You'll never see a score or an assessment here \u2014 that goes to "
               "your consultant, not to you.")

# ======================================================== CONSULTANT VIEW ==
else:
    b = briefmod.assemble(s)
    state = b["state"]

    head = st.columns([3, 1, 1])
    head[0].markdown(f"#### Discovery brief \u2014 {s.company or s.founder_name or 'untitled'}")
    head[1].metric("Coverage", f"{b['coverage_pct']:.0%}")
    head[2].metric("Claims", len(b["claims"]))

    st.markdown(
        f'<span class="chip" style="background:{STATE_COLOR[state]}">'
        f'{STATE_LABEL[state]}</span>'
        + ('  <span class="cite">overridden by consultant</span>' if b["state_overridden"] else ""),
        unsafe_allow_html=True)

    # --- the readiness signal, or its deliberate absence -------------------
    st.write("")
    if b["recommendation"]:
        st.success(f"**{b['recommendation']['shape']}** \u2014 {b['recommendation']['why']}")
    else:
        st.markdown(
            '<div class="absent"><b>No engagement shape recommended.</b><br>'
            'The brief is below threshold, so the system emits nothing rather than a '
            'weaker recommendation. What is missing is listed below.</div>',
            unsafe_allow_html=True)
    for r in b["reasons"]:
        st.markdown(f'<div class="cite">\u2014 {r}</div>', unsafe_allow_html=True)

    tabs = st.tabs(["Outstanding", "Claims", "Coverage", "Narrative", "Audit"])

    with tabs[0]:
        if not b["outstanding"]:
            st.write("Nothing outstanding.")
        for o in b["outstanding"]:
            icon = "\u25c9" if o["priority"] == 1 else "\u25cb"
            st.markdown(f"{icon} **{o['text']}**")
            if o["claim"]:
                st.markdown(f'<div class="cite">claim: \u201c{o["claim"][:150]}\u201d</div>',
                            unsafe_allow_html=True)

    with tabs[1]:
        if not b["claims"]:
            st.write("No claims extracted yet.")
        for c in b["claims"]:
            st.markdown(
                f'<div class="claim"><span class="chip" style="background:{GRADE_COLOR[c.grade]}">'
                f'{GRADE_LABEL[c.grade]}</span>'
                f'{"  <b>load-bearing</b>" if c.load_bearing else ""}<br>{c.text}<br>'
                f'<span class="cite">{c.item_id or "\u2014"} \u00b7 cited from turn t{c.citation_turn}'
                f'{" \u00b7 artifact: " + c.artifact if c.artifact else ""}'
                f'{" \u00b7 owner: " + c.named_owner if c.named_owner else ""}</span></div>',
                unsafe_allow_html=True)
            if c.escalated:
                st.markdown(f'<div class="rule"><b>Escalation rule fired.</b> {c.note}</div>',
                            unsafe_allow_html=True)
            cols = st.columns([1, 3])
            new = cols[0].selectbox("Override", [c.grade] + [g for g in GRADE_LABEL if g != c.grade],
                                    key=f"ov{c.id}", label_visibility="collapsed")
            if new != c.grade:
                if cols[1].button("Apply override", key=f"ap{c.id}"):
                    s.log("override", {"claim": c.id, "from": c.grade, "to": new, "by": "consultant"})
                    c.override_from, c.grade, c.overridden_by = c.grade, new, "consultant"
                    persist()
                    st.rerun()
            st.write("")

    with tabs[2]:
        for section in sorted({i.section for i in playbook.ITEMS}):
            st.markdown(f"**{section}**")
            for i in [x for x in playbook.ITEMS if x.section == section]:
                stt = b["coverage"][i.id]
                mark = {COVERED: "\u25cf", PARTIAL: "\u25d0", NOT_DISCUSSED: "\u25cb"}[stt]
                lb = " **·load-bearing**" if i.load_bearing else ""
                st.markdown(f'{mark} `{i.id}` {i.text[:78]}{lb}')
            st.write("")

    with tabs[3]:
        n = b["narrative"]
        st.write(n.get("summary", ""))
        if n.get("contradictions"):
            st.markdown("**Contradictions**")
            for c in n["contradictions"]:
                st.markdown(f"- {c}")
        st.info(n.get("not_discussed_note", ""))

    with tabs[4]:
        if b["quarantined"]:
            st.markdown("**Quarantined input** \u2014 excluded from grading, preserved for review")
            for t in b["quarantined"]:
                st.markdown(f'<div class="rule">t{t.idx} \u00b7 {t.quarantine_reason}<br>'
                            f'<span class="cite">{t.text[:300]}</span></div>',
                            unsafe_allow_html=True)
            st.write("")
        st.markdown("**Event log**")
        for a in reversed(s.audit[-40:]):
            st.markdown(f'<div class="cite">{a["at"]} \u00b7 {a["event"]} \u00b7 {a["detail"]}</div>',
                        unsafe_allow_html=True)

    st.divider()
    ov = st.selectbox("Override the readiness signal",
                      ["\u2014"] + [STATE_LABEL[k] for k in (SCOPE_READY, BRIEF_PARTIAL, INSUFFICIENT)])
    if ov != "\u2014" and st.button("Apply signal override"):
        key = [k for k, v in STATE_LABEL.items() if v == ov][0]
        s.log("signal_override", {"from": state, "to": key, "by": "consultant"})
        s.signal_override = key
        persist()
        st.rerun()
    st.caption(f"Brief produced under playbook `{b['playbook_version']}`. "
               "Nothing here has been shown to the founder.")

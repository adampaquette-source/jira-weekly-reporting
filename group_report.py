#!/usr/bin/env python3
"""
Per-department (cross-functional group) report generator.

Produces a stakeholder-facing summary for one consuming department (e.g. Sales)
from the same weekly Jira snapshots the movement report uses, PLUS:
  - dept-map.json        : resolves each issue -> department(s) (label + epic + key overrides)
  - comments/<date>.json : plain-English status notes (agent-summarized from Jira comments)

Audience is the group's business leader, not the dev team: plain language,
outcome-first, grouped into Shipped / In flight / New / Up next / Aging.

The data is computed ONCE, then rendered two ways:
  - VIEW  : a self-contained .html with a <style> block, for browsing/sharing a file.
  - EMAIL : a .email.html with **inline styles only** (no <style>/<head>), so it survives
            being pasted into a Gmail draft / forwarded to Outlook, which strip <style>.
            This is the body the Google Apps Script in distribution/ embeds and sends.

Membership for a department D (union):
  - any issue label L where dept_map.label_to_dept[L] == D
  - issue.parent in dept_map.epic_to_dept and D in that list   (Jira labels don't inherit to children)
  - issue.key in dept_map.key_overrides and D in that list

"In flight" vs "Up next" is by workflow stage, not status category, because this Jira's
QA/UAT statuses live in the "To Do" category after a 2026-03 migration.

Usage:
  python3 group_report.py Sales
  python3 group_report.py Sales PREV.json CUR.json
"""

import json, os, sys, datetime, html, glob
import diff_report as dr  # reuse compute(), loaders, STALE_DAYS

HERE = os.path.dirname(os.path.abspath(__file__))
SNAP_DIR = os.path.join(HERE, "snapshots")
# Stakeholder-facing per-department reports live in a "Department Reports" subfolder
# (./Department Reports/<Department>), kept separate from the internal movement
# reports under ./reports/ so they're easy to find and share.
REP_DIR = os.path.join(HERE, "Department Reports")

STALE_NOTE_DAYS = 14         # a status note older than this is flagged "may be stale"
DROP_UNASSIGNED_AGING_DAYS = 60  # hide unassigned queued items idle longer than this (likely dead)

# Workflow stage: 0 = not started/queued, 1-4 = actively in flight, 5 = done.
STAGE = {
    "to do": 0, "not started": 0, "open": 0, "backlog": 0, "ready for dev": 0,
    "in progress": 1, "in development": 1,
    "in qa": 2, "ready for qa": 2,
    "in uat": 3, "ready for uat": 3,
    "ready to deploy": 4, "ready for deploy": 4,
    "done": 5, "closed": 5, "resolved": 5,
}
STAGE_LABEL = {0: "Queued", 1: "Building", 2: "Testing (QA)",
               3: "Testing (UAT)", 4: "Ready to deploy", 5: "Done"}

def stage(status):
    return STAGE.get((status or "").strip().lower(), 1)

def is_open(i):
    return (i.get("cat") or "").lower() != "done"

def load_json(p):
    with open(p) as f:
        return json.load(f)

# ---------- dept resolution ----------

def resolve_depts(issue, dm):
    depts = set()
    # whole-project routing (e.g. TDDE -> Domo) by key prefix
    proj = issue["key"].split("-")[0]
    for d in dm.get("project_to_dept", {}).get(proj, []):
        depts.add(d)
    for lab in issue.get("labels") or []:
        d = dm["label_to_dept"].get(lab)
        if d:
            depts.add(d)
    par = issue.get("parent")
    if par and par in dm.get("epic_to_dept", {}):
        depts.update(dm["epic_to_dept"][par])
    if issue["key"] in dm.get("key_overrides", {}):
        depts.update(dm["key_overrides"][issue["key"]])
    return depts

def admin_dept(issue, dm):
    """Recommended (not-yet-tagged) NetSuite-admin department, or None."""
    return dm.get("admin_recommendations", {}).get(issue["key"])

def domo_fold_depts(issue, dm):
    """Cross-functional group(s) a Domo/TDDE item folds into, beyond the standalone Domo report."""
    return dm.get("domo_subdept", {}).get(issue["key"], [])

# ---------- styling (single source -> class block for VIEW, inlined for EMAIL) ----------
# Each value is a CSS declaration list ending in ';' so they can be concatenated when inlined.
STYLES = {
    "wrap": "max-width:880px;margin:0 auto;padding:24px 20px 50px;font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;color:#1f2733;line-height:1.45;",
    "h1": "font-size:22px;margin:0 0 2px;color:#1F3864;",
    "sub": "color:#5b6776;font-size:13px;margin:0 0 16px;",
    "tldr": "background:#ffffff;border:1px solid #e3e8ef;border-left:4px solid #2E75B6;border-radius:8px;padding:13px 15px;margin:0 0 16px;font-size:14px;",
    "pill": "display:inline-block;background:#ffffff;border:1px solid #e3e8ef;border-radius:8px;padding:8px 12px;margin:0 8px 8px 0;font-size:13px;min-width:84px;vertical-align:top;",
    "pillnum": "display:block;font-size:22px;line-height:1.1;font-weight:700;",
    "c-good": "color:#1a7f4b;", "c-move": "color:#2E75B6;", "c-new": "color:#6c3fb5;",
    "c-warn": "color:#c0392b;", "c-plain": "color:#1f2733;",
    "h2": "font-size:16px;color:#1F3864;margin:22px 0 4px;",
    "sechint": "color:#8a96a3;font-size:12px;margin:0 0 10px;",
    "item": "background:#ffffff;border:1px solid #e3e8ef;border-radius:8px;padding:11px 13px;margin:0 0 9px;",
    "title": "font-weight:600;font-size:14px;",
    "meta": "color:#5b6776;font-size:12px;margin-top:3px;",
    "stg": "display:inline-block;padding:2px 8px;border-radius:11px;font-size:11px;font-weight:600;margin-left:6px;",
    "stg0": "background:#eceff3;color:#5b6776;", "stg1": "background:#fdf0d5;color:#9a6b00;",
    "stg2": "background:#e7f0fb;color:#2E75B6;", "stg3": "background:#efe7fb;color:#6c3fb5;",
    "stg4": "background:#e3f5ea;color:#1a7f4b;", "stg5": "background:#e3f5ea;color:#1a7f4b;",
    "note": "font-size:13px;color:#33414f;margin-top:6px;",
    "who": "color:#8a96a3;font-size:11px;",
    "stale": "color:#c0392b;font-weight:600;",
    "moved": "color:#2E75B6;font-size:12px;font-weight:600;margin-top:5px;",
    "child": "margin:6px 0 0 14px;padding-left:10px;border-left:2px solid #eef1f5;font-size:13px;",
    "empty": "color:#8a96a3;font-style:italic;font-size:13px;margin:0 0 8px;",
    "multi": "color:#8a96a3;font-size:11px;",
    "foot": "margin-top:30px;color:#8a96a3;font-size:11px;border-top:1px solid #e3e8ef;padding-top:12px;",
    "lnk": "color:#2E75B6;text-decoration:none;",
    "exec": "background:#ffffff;border:1px solid #e3e8ef;border-left:4px solid #2E75B6;border-radius:8px;padding:14px 16px;margin:0 0 22px;",
    "exectitle": "font-size:12px;font-weight:700;color:#1F3864;letter-spacing:.05em;text-transform:uppercase;margin:0 0 6px;",
    "execlbl": "font-size:12px;font-weight:700;color:#2E75B6;margin:9px 0 1px;",
    "ulst": "margin:0;padding-left:20px;",
    "li": "font-size:13px;color:#33414f;margin:2px 0;",
    "muted": "color:#8a96a3;font-size:12px;",
    "ainote": "background:#f5f7fa;border:1px solid #e3e8ef;border-radius:8px;padding:10px 13px;margin:0 0 16px;font-size:12px;color:#5b6776;line-height:1.5;",
}

class R:
    """Renderer carrying the output mode."""
    def __init__(self, mode):
        self.mode = mode  # "view" | "email"
    def a(self, *names):
        if self.mode == "view":
            return f'class="{" ".join(names)}"'
        return f'style="{"".join(STYLES[n] for n in names)}"'

def esc(s):
    return html.escape(str(s if s is not None else ""))

def link(r, i):
    return f'<a href="{esc(i.get("url"))}" {r.a("lnk")} target="_blank">{esc(i["key"])}</a>'

def stage_badge(r, status):
    s = stage(status)
    return f'<span {r.a("stg", f"stg{s}")}>{esc(STAGE_LABEL[s])}</span>'

def note_html(r, key, notes, ref):
    n = notes.get(key)
    if not n:
        return ""
    d = n.get("date"); flag = ""
    if d:
        try:
            age = (ref - datetime.date.fromisoformat(d)).days
            if age > STALE_NOTE_DAYS:
                flag = f' <span {r.a("stale")}>· may be stale ({age}d old)</span>'
        except ValueError:
            pass
    who = f'{esc(n.get("author","?"))}, {esc(d)}' if d else esc(n.get("author", "?"))
    return (f'<div {r.a("note")}>{esc(n["summary"])}'
            f'<div {r.a("who")}>— {who}{flag}</div></div>')

def item_html(r, i, notes, ref, transitions, focus, children=None):
    moved = ""
    t = transitions.get(i["key"])
    if t:
        moved = f'<div {r.a("moved")}>↑ moved {esc(t[0])} → {esc(t[1])} this week</div>'
    extra = [d for d in i.get("_depts", []) if d != focus]
    multi = f' <span {r.a("multi")}>· also {esc(", ".join(sorted(extra)))}</span>' if extra else ""
    out = (f'<div {r.a("item")}>'
           f'<div {r.a("title")}>{esc(i.get("summary"))}{stage_badge(r, i.get("status"))}</div>'
           f'<div {r.a("meta")}>{link(r, i)} · {esc(i.get("assignee") or "Unassigned")}{multi}</div>'
           f'{moved}{note_html(r, i["key"], notes, ref)}')
    for c in (children or []):
        out += (f'<div {r.a("child")}><b>{esc(c.get("summary"))}</b> '
                f'{stage_badge(r, c.get("status"))} '
                f'<span {r.a("meta")}>{link(r, c)} · {esc(c.get("assignee") or "Unassigned")}</span></div>')
    return out + "</div>"

def simple_rows(r, items):
    if not items:
        return f'<div {r.a("empty")}>Nothing this week.</div>'
    return "".join(
        f'<div {r.a("item")}><div {r.a("title")}>{esc(i.get("summary"))}{stage_badge(r, i.get("status"))}</div>'
        f'<div {r.a("meta")}>{link(r, i)} · {esc(i.get("assignee") or "Unassigned")}</div></div>'
        for i in items)

def aging_rows(r, items):
    if not items:
        return f'<div {r.a("empty")}>None.</div>'
    return "".join(
        f'<div {r.a("item")}><div {r.a("title")}>{esc(i.get("summary"))}</div>'
        f'<div {r.a("meta")}>{link(r, i)} · {esc(i.get("assignee") or "Unassigned")} · '
        f'<span {r.a("stale")}>{i["idle"]}d idle</span></div></div>' for i in items)

def pill(r, n, label, color):
    return (f'<div {r.a("pill")}><span {r.a("pillnum", color)}>{n}</span>{esc(label)}</div>')

def note_meta(n, ref):
    d = n.get("date"); flag = ""
    if d:
        try:
            age = (ref - datetime.date.fromisoformat(d)).days
            if age > STALE_NOTE_DAYS:
                flag = f' · may be stale ({age}d)'
        except ValueError:
            pass
    return f'{esc(n.get("author","?"))}, {esc(d)}{flag}' if d else esc(n.get("author","?"))

def exec_block(r, d):
    """Executive summary = LLM-curated top callouts (2-5), authored in exec/<date>.json.
    No sub-headings — just the most important things by inferred importance. Falls back to
    the one-line auto summary if no curated bullets exist for this department."""
    bullets = d.get("exec_bullets") or [d["tldr"]]
    lis = "".join(f'<li {r.a("li")}>{esc(b)}</li>' for b in bullets)
    return (f'<div {r.a("exec")}>'
            f'<div {r.a("exectitle")}>Executive summary</div>'
            f'<ul {r.a("ulst")}>{lis}</ul></div>')

# ---------- compute ----------

def compute(dept, prev, cur, dm, comments):
    ref = datetime.date.fromisoformat(cur["captured_at"][:10])
    ck = {i["key"]: i for i in cur["issues"]}
    for i in cur["issues"]:
        i["_depts"] = sorted(resolve_depts(i, dm))
    members = {k: i for k, i in ck.items() if dept in i["_depts"]}

    buckets, _ = dr.compute(prev, cur)
    progressed = [m for m in buckets["progressed"] if dept in ck.get(m["key"], {}).get("_depts", [])]
    transitions = {m["key"]: (m.get("from"), m.get("to")) for m in progressed}
    completed = [i for i in buckets["completed"] if dept in ck.get(i["key"], {}).get("_depts", [])]
    created_keys = {i["key"] for i in buckets["created"]}

    # Buckets (each open primary item lands in exactly one): in flight (actively worked),
    # new this week, next sprint (committed to current/next sprint, not started), or backlog.
    in_flight, new_this_week, next_sprint, backlog = [], [], [], []
    dropped = 0
    for k, i in members.items():
        if not is_open(i):
            continue
        st = stage(i.get("status"))
        idle = dr.days_since(i.get("updated"), ref)
        unassigned = i.get("assignee") in (None, "Unassigned")
        if 1 <= st <= 4:
            in_flight.append(i)
        elif k in created_keys:
            new_this_week.append(i)
        elif i.get("sprint"):
            next_sprint.append(i)
        else:
            if unassigned and idle is not None and idle > DROP_UNASSIGNED_AGING_DAYS:
                dropped += 1            # hide likely-dead unassigned backlog
                continue
            backlog.append({**i, "idle": idle if (idle is not None and idle >= dr.STALE_DAYS) else None})

    inflight_keys = {i["key"] for i in in_flight}
    child_map = {}
    for i in in_flight:
        par = i.get("parent")
        if par and par in inflight_keys:
            child_map.setdefault(par, []).append(i)
    top_inflight = [i for i in in_flight if not (i.get("parent") in inflight_keys)]
    top_inflight.sort(key=lambda i: (-(i["key"] in child_map), -stage(i.get("status"))))
    next_sprint.sort(key=lambda i: (i.get("assignee") in (None, "Unassigned"), i.get("summary") or ""))
    new_this_week.sort(key=lambda i: i.get("summary") or "")
    backlog.sort(key=lambda i: (i.get("assignee") in (None, "Unassigned"), -(i.get("idle") or 0)))

    bits = [f"{len(completed)} shipped" if completed else None,
            f"{len(in_flight)} in flight",
            f"{len(new_this_week)} new" if new_this_week else None,
            f"{len(next_sprint)} queued for next sprint" if next_sprint else None,
            f"{len(backlog)} in backlog" if backlog else None]
    tldr = f"This week for {dept}: " + ", ".join(b for b in bits if b) + "."

    # extra lanes (suppressed on the standalone Domo report itself)
    admin_lane, domo_lane = [], []
    if dept != "Domo":
        for i in cur["issues"]:
            if not is_open(i):
                continue
            if admin_dept(i, dm) == dept:
                admin_lane.append(i)
            if dept in domo_fold_depts(i, dm):
                domo_lane.append(i)
        admin_lane.sort(key=lambda i: (-stage(i.get("status")), i["key"]))
        domo_lane.sort(key=lambda i: (-stage(i.get("status")), i["key"]))

    return {
        "dept": dept, "ref": ref, "tldr": tldr,
        "completed": completed, "top_inflight": top_inflight, "child_map": child_map,
        "in_flight_count": len(in_flight), "new": new_this_week,
        "next_sprint": next_sprint, "backlog": backlog, "dropped": dropped,
        "transitions": transitions, "notes": comments.get("notes", {}),
        "admin_lane": admin_lane, "domo_lane": domo_lane, "progressed": progressed,
    }

# ---------- render ----------

def style_block():
    rules = "".join(f".{name}{{{decl}}}" for name, decl in STYLES.items() if not name.startswith("lnk"))
    rules += f"a.lnk{{{STYLES['lnk']}}}a.lnk:hover{{text-decoration:underline}}body{{background:#f4f6f9;margin:0}}"
    return rules

def render(d, mode):
    r = R(mode)
    dept, ref = d["dept"], d["ref"]
    summary = exec_block(r, d)
    pfx = "" if dept == "Domo" else "Dev — "
    secs = []

    # 1. Shipped + In Flight
    inflight = "".join(item_html(r, i, d["notes"], ref, d["transitions"], dept, d["child_map"].get(i["key"]))
                       for i in d["top_inflight"])
    sif = (simple_rows(r, d["completed"]) if d["completed"] else "") + inflight
    if not d["completed"] and not d["top_inflight"]:
        sif = f'<div {r.a("empty")}>Nothing shipped or in flight.</div>'
    secs.append(f'<div {r.a("h2")}>{pfx}Shipped + In Flight</div>'
                f'<div {r.a("sechint")}>Completed this week plus work actively being built or tested. '
                f'Status notes come from the team\'s Jira card updates.</div>' + sif)

    # 2. New Requests
    secs.append(f'<div {r.a("h2")}>{pfx}New Requests</div>'
                f'<div {r.a("sechint")}>Came into the queue this week.</div>' + simple_rows(r, d["new"]))

    # 3. Next Sprint
    secs.append(f'<div {r.a("h2")}>{pfx}Next Sprint</div>'
                f'<div {r.a("sechint")}>Committed to the current or upcoming sprint, not yet started.</div>'
                + simple_rows(r, d["next_sprint"]))

    # 4. Admin (NetSuite-admin recs, not yet labeled) — business reports only
    if d.get("admin_lane"):
        secs.append(f'<div {r.a("h2")}>Admin — pending tagging ({len(d["admin_lane"])})</div>'
                    f'<div {r.a("sechint")}>NetSuite-admin (NA) items that look like {esc(dept)} work — '
                    f'high-confidence recommendations awaiting the admin team\'s Jira labels (target: this Friday). '
                    f'Not yet in the counts above.</div>' + simple_rows(r, d["admin_lane"]))

    # 5. Domo / BI folded in from the Domo (TDDE) project — business reports only
    if d.get("domo_lane"):
        secs.append(f'<div {r.a("h2")}>Domo / BI ({len(d["domo_lane"])})</div>'
                    f'<div {r.a("sechint")}>Domo dashboards &amp; data feeds related to {esc(dept)}. '
                    f'The full Domo backlog is in the dedicated Domo report.</div>'
                    + simple_rows(r, d["domo_lane"]))

    # 6. Backlog
    def bl(i):
        idle = f' · <span {r.a("stale")}>{i["idle"]}d idle</span>' if i.get("idle") else ""
        return (f'<div {r.a("item")}><div {r.a("title")}>{esc(i.get("summary"))}</div>'
                f'<div {r.a("meta")}>{link(r, i)} · {esc(i.get("assignee") or "Unassigned")}{idle}</div></div>')
    bhint = f'Open {esc(dept)} items not committed to the next sprint, oldest-idle first.'
    if d["dropped"]:
        bhint += (f' ({d["dropped"]} unassigned item{"s" if d["dropped"]!=1 else ""} '
                  f'idle &gt;{DROP_UNASSIGNED_AGING_DAYS}d hidden as likely-dead.)')
    backlog_html = "".join(bl(i) for i in d["backlog"]) or f'<div {r.a("empty")}>Empty.</div>'
    secs.append(f'<div {r.a("h2")}>Backlog</div><div {r.a("sechint")}>{bhint}</div>' + backlog_html)

    ainote = (f'<div {r.a("ainote")}>'
              f'<b>About this report:</b> it&rsquo;s generated with AI from the team&rsquo;s Jira activity, '
              f'and it can be tailored to suit your team&rsquo;s needs &mdash; what&rsquo;s included, how it&rsquo;s '
              f'grouped, and the level of detail. Please send any feedback or adjustment requests to '
              f'<a href="mailto:adam.paquette@pcstools.com" {r.a("lnk")}>adam.paquette@pcstools.com</a>.'
              f'</div>')
    body = (f'<div {r.a("wrap")}>'
            f'<div {r.a("h1")}>IT Work for {esc(dept)}</div>'
            f'<div {r.a("sub")}>Week of {esc(ref.isoformat())} &nbsp;·&nbsp; prepared by Adam Paquette (interim IT PM)</div>'
            f'{ainote}'
            f'<div {r.a("tldr")}>{esc(d["tldr"])}</div>'
            f'{summary}'
            f'{"".join(secs)}'
            f'<div {r.a("foot")}>Auto-generated from Jira (projects TTD + NA + TDDE) and the team\'s card comments. '
            f'Status notes are summarized from each card\'s latest Jira comment. To request or reprioritize work, reply to Adam.</div>'
            f'</div>')
    if mode == "view":
        return (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
                f'<meta name="viewport" content="width=device-width,initial-scale=1">'
                f'<title>IT Work for {esc(dept)} — {esc(ref.isoformat())}</title>'
                f'<style>{style_block()}</style></head><body>{body}</body></html>')
    # email: inline styles only, no <head>/<style>
    return (f'<!doctype html><html><body style="margin:0;background:#f4f6f9;">{body}</body></html>')

# ---------- main ----------

def main():
    args = sys.argv[1:]
    dept = args[0] if args else "Sales"
    dm = load_json(os.path.join(HERE, "dept-map.json"))
    if len(args) >= 3:
        prev, cur = load_json(args[1]), load_json(args[2])
    else:
        files = sorted(glob.glob(os.path.join(SNAP_DIR, "*.json")))
        if len(files) < 2:
            print("Need two snapshots."); sys.exit(1)
        prev, cur = load_json(files[-2]), load_json(files[-1])
    cdate = cur["captured_at"][:10]
    cpath = os.path.join(HERE, "comments", f"{cdate}.json")
    comments = load_json(cpath) if os.path.exists(cpath) else {"notes": {}}
    epath = os.path.join(HERE, "exec", f"{cdate}.json")
    execmap = load_json(epath) if os.path.exists(epath) else {}

    d = compute(dept, prev, cur, dm, comments)
    d["exec_bullets"] = execmap.get(dept)
    dept_dir = os.path.join(REP_DIR, dept)
    os.makedirs(dept_dir, exist_ok=True)
    slug = dept.lower().replace(" ", "-")
    view_path = os.path.join(dept_dir, f"{slug}-{cdate}.html")
    email_path = os.path.join(dept_dir, f"{slug}-{cdate}.email.html")
    with open(view_path, "w") as f:
        f.write(render(d, "view"))
    with open(email_path, "w") as f:
        f.write(render(d, "email"))

    print(f"View : {view_path}")
    print(f"Email: {email_path}")
    print(f"{dept}: shipped={len(d['completed'])} in_flight={d['in_flight_count']} "
          f"new={len(d['new'])} next_sprint={len(d['next_sprint'])} "
          f"backlog={len(d['backlog'])} admin={len(d['admin_lane'])} domo={len(d['domo_lane'])} "
          f"exec={'authored' if d.get('exec_bullets') else 'fallback'} (hidden={d['dropped']})")

if __name__ == "__main__":
    main()

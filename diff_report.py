#!/usr/bin/env python3
"""
Weekly Jira movement report generator (deterministic).

Reads compact snapshot JSON files from ./snapshots/ and writes a self-contained
HTML movement report to ./reports/. The Jira *fetch* is done by the scheduled-task
agent (it writes the snapshot); this script does the diff + report so the heavy
logic is reproducible and not dependent on an LLM eyeballing data.

Snapshot JSON schema:
{
  "captured_at": "YYYY-MM-DD",
  "projects": ["TTD", "NA"],
  "issues": [
    {"key","summary","status","cat","assignee","type","created","updated","due","url"}
  ]
}
- "cat" is the Jira status category name: "To Do" | "In Progress" | "Done".
- Snapshots include the OPEN universe (cat != Done) plus anything resolved in the
  last ~10 days (cat == Done) so completions can be detected across runs.

Usage:
  python3 diff_report.py                  # auto: diff two latest snapshots
  python3 diff_report.py PREV.json CUR.json
  python3 diff_report.py --baseline CUR.json   # single-snapshot baseline report
"""

import json, sys, os, glob, datetime, html

HERE = os.path.dirname(os.path.abspath(__file__))
SNAP_DIR = os.path.join(HERE, "snapshots")
REP_DIR = os.path.join(HERE, "reports")
STALE_DAYS = 21  # open + untouched longer than this = stalled

# Workflow ordering so we can label transitions as forward / backward.
STATUS_ORDER = {
    "to do": 0, "not started": 0, "open": 0, "backlog": 0,
    "in progress": 1, "in development": 1,
    "in qa": 2,
    "in uat": 3,
    "ready to deploy": 4,
    "done": 5, "closed": 5, "resolved": 5,
}

def order(status):
    return STATUS_ORDER.get((status or "").strip().lower(), 1)

def load(path):
    with open(path) as f:
        return json.load(f)

def by_key(snap):
    return {i["key"]: i for i in snap.get("issues", [])}

def is_open(i):
    return (i.get("cat") or "").lower() != "done"

def days_since(date_str, ref):
    if not date_str:
        return None
    try:
        d = datetime.date.fromisoformat(date_str[:10])
    except ValueError:
        return None
    return (ref - d).days

# ---------- diff ----------

def compute(prev, cur):
    pk, ck = by_key(prev), by_key(cur)
    ref = datetime.date.fromisoformat(cur["captured_at"][:10])
    buckets = {k: [] for k in
               ["created", "completed", "progressed", "regressed",
                "reassigned", "reopened", "stalled", "open_all"]}

    for key, c in ck.items():
        p = pk.get(key)
        # current open set
        if is_open(c):
            buckets["open_all"].append(c)
            d = days_since(c.get("updated"), ref)
            if d is not None and d >= STALE_DAYS:
                buckets["stalled"].append({**c, "idle_days": d})
        # new this period
        if p is None and is_open(c):
            buckets["created"].append(c)
            continue
        if p is None:
            continue
        # completed
        if is_open(p) and not is_open(c):
            buckets["completed"].append(c)
            continue
        # reopened
        if not is_open(p) and is_open(c):
            buckets["reopened"].append(c)
        # status movement
        if (p.get("status") or "") != (c.get("status") or ""):
            move = {**c, "from": p.get("status"), "to": c.get("status")}
            if order(c.get("status")) > order(p.get("status")):
                buckets["progressed"].append(move)
            else:
                buckets["regressed"].append(move)
        # reassignment
        if (p.get("assignee") or "") != (c.get("assignee") or ""):
            buckets["reassigned"].append(
                {**c, "from": p.get("assignee") or "Unassigned",
                 "to": c.get("assignee") or "Unassigned"})
    return buckets, ref

def baseline_buckets(cur):
    ref = datetime.date.fromisoformat(cur["captured_at"][:10])
    ck = by_key(cur)
    b = {k: [] for k in ["created", "completed", "progressed", "regressed",
                         "reassigned", "reopened", "stalled", "open_all"]}
    for c in ck.values():
        if is_open(c):
            b["open_all"].append(c)
            d = days_since(c.get("updated"), ref)
            if d is not None and d >= STALE_DAYS:
                b["stalled"].append({**c, "idle_days": d})
            cd = days_since(c.get("created"), ref)
            if cd is not None and cd <= 7:
                b["created"].append(c)
    return b, ref

# ---------- per-person ----------

def load_table(open_all, completed):
    people = {}
    for i in open_all:
        a = i.get("assignee") or "Unassigned"
        people.setdefault(a, {"open": 0, "done": 0, "inprog": 0})
        people[a]["open"] += 1
        if (i.get("cat") or "").lower() == "in progress":
            people[a]["inprog"] += 1
    for i in completed:
        a = i.get("assignee") or "Unassigned"
        people.setdefault(a, {"open": 0, "done": 0, "inprog": 0})
        people[a]["done"] += 1
    return dict(sorted(people.items(), key=lambda kv: -kv[1]["open"]))

# ---------- html ----------

CSS = """
:root{color-scheme:light}
*{box-sizing:border-box}
body{font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;margin:0;background:#f5f7fa;color:#1f2733}
.wrap{max-width:1080px;margin:0 auto;padding:28px 22px 60px}
h1{font-size:24px;margin:0 0 2px;color:#1F3864}
.sub{color:#5b6776;font-size:13px;margin-bottom:22px}
.cards{display:flex;flex-wrap:wrap;gap:12px;margin-bottom:26px}
.card{flex:1;min-width:120px;background:#fff;border:1px solid #e3e8ef;border-radius:10px;padding:14px 16px}
.card .n{font-size:28px;font-weight:700;line-height:1}
.card .l{font-size:12px;color:#5b6776;margin-top:4px}
.card.good .n{color:#1a7f4b}.card.move .n{color:#2E75B6}.card.warn .n{color:#c0392b}.card.new .n{color:#6c3fb5}
h2{font-size:16px;color:#1F3864;margin:26px 0 10px;border-bottom:2px solid #2E75B6;padding-bottom:5px}
table{width:100%;border-collapse:collapse;background:#fff;border:1px solid #e3e8ef;border-radius:10px;overflow:hidden;font-size:13px}
th{background:#1F3864;color:#fff;text-align:left;padding:8px 10px;font-weight:600}
td{padding:8px 10px;border-top:1px solid #eef1f5;vertical-align:top}
tr:nth-child(even) td{background:#fafbfc}
a{color:#2E75B6;text-decoration:none}a:hover{text-decoration:underline}
.badge{display:inline-block;padding:2px 8px;border-radius:11px;font-size:11px;font-weight:600;white-space:nowrap}
.b-todo{background:#eceff3;color:#5b6776}.b-prog{background:#fdf0d5;color:#9a6b00}.b-done{background:#e3f5ea;color:#1a7f4b}
.arrow{color:#2E75B6;font-weight:700}
.idle{color:#c0392b;font-weight:600}
.empty{color:#8a96a3;font-style:italic;padding:10px 2px;font-size:13px}
.proj{font-size:11px;color:#8a96a3;font-weight:600}
.bar{height:10px;background:#eceff3;border-radius:5px;overflow:hidden;display:inline-block;width:120px;vertical-align:middle}
.bar>span{display:block;height:100%;background:#2E75B6}
.foot{margin-top:30px;color:#8a96a3;font-size:11px}
"""

def cat_badge(cat):
    c = (cat or "").lower()
    if c == "done": return '<span class="badge b-done">Done</span>'
    if c == "in progress": return '<span class="badge b-prog">In&nbsp;Progress</span>'
    return '<span class="badge b-todo">To&nbsp;Do</span>'

def esc(s): return html.escape(str(s if s is not None else ""))

def link(i):
    return f'<a href="{esc(i.get("url"))}" target="_blank">{esc(i["key"])}</a>'

def rows_basic(items, extra_label=None, extra_key=None):
    if not items:
        return '<div class="empty">None this week.</div>'
    out = ['<table><tr><th>Key</th><th>Summary</th><th>Status</th><th>Assignee</th>']
    if extra_label: out.append(f'<th>{esc(extra_label)}</th>')
    out.append('</tr>')
    for i in items:
        out.append('<tr>'
            f'<td>{link(i)} <span class="proj">{esc(i["key"].split("-")[0])}</span></td>'
            f'<td>{esc(i.get("summary"))}</td>'
            f'<td>{cat_badge(i.get("cat"))} {esc(i.get("status"))}</td>'
            f'<td>{esc(i.get("assignee") or "Unassigned")}</td>')
        if extra_key:
            v = i.get(extra_key)
            if extra_key == "idle_days": v = f'<span class="idle">{v}d idle</span>'
            out.append(f'<td>{v}</td>')
        out.append('</tr>')
    out.append('</table>')
    return "".join(out)

def rows_transition(items):
    if not items:
        return '<div class="empty">None this week.</div>'
    out = ['<table><tr><th>Key</th><th>Summary</th><th>Movement</th><th>Assignee</th></tr>']
    for i in items:
        out.append('<tr>'
            f'<td>{link(i)} <span class="proj">{esc(i["key"].split("-")[0])}</span></td>'
            f'<td>{esc(i.get("summary"))}</td>'
            f'<td>{esc(i.get("from"))} <span class="arrow">&rarr;</span> {esc(i.get("to"))}</td>'
            f'<td>{esc(i.get("assignee") or "Unassigned")}</td></tr>')
    out.append('</table>')
    return "".join(out)

def rows_reassign(items):
    if not items:
        return '<div class="empty">None this week.</div>'
    out = ['<table><tr><th>Key</th><th>Summary</th><th>Reassigned</th></tr>']
    for i in items:
        out.append('<tr>'
            f'<td>{link(i)} <span class="proj">{esc(i["key"].split("-")[0])}</span></td>'
            f'<td>{esc(i.get("summary"))}</td>'
            f'<td>{esc(i.get("from"))} <span class="arrow">&rarr;</span> {esc(i.get("to"))}</td></tr>')
    out.append('</table>')
    return "".join(out)

def load_rows(table):
    if not table:
        return '<div class="empty">No open work.</div>'
    mx = max((v["open"] for v in table.values()), default=1) or 1
    out = ['<table><tr><th>Assignee</th><th>Open</th><th>In&nbsp;progress</th>'
           '<th>Completed&nbsp;this&nbsp;week</th><th>Load</th></tr>']
    for name, v in table.items():
        pct = int(100 * v["open"] / mx)
        out.append('<tr>'
            f'<td>{esc(name)}</td><td>{v["open"]}</td><td>{v["inprog"]}</td>'
            f'<td>{v["done"]}</td>'
            f'<td><span class="bar"><span style="width:{pct}%"></span></span></td></tr>')
    out.append('</table>')
    return "".join(out)

def card(n, label, cls=""):
    return f'<div class="card {cls}"><div class="n">{n}</div><div class="l">{esc(label)}</div></div>'

def build_html(buckets, ref, prev_date, projects, baseline=False):
    table = load_table(buckets["open_all"], buckets["completed"])
    stalled = sorted(buckets["stalled"], key=lambda x: -x.get("idle_days", 0))
    title_range = (f"Week ending {ref.isoformat()}" if baseline
                   else f"{prev_date} &rarr; {ref.isoformat()}")
    mode = "Baseline (first run)" if baseline else "Weekly movement"
    cards = [
        card(len(buckets["created"]), "New this week", "new"),
        card(len(buckets["progressed"]), "Progressed", "move"),
        card(len(buckets["completed"]), "Completed", "good"),
        card(len(buckets["stalled"]), f"Stalled (≥{STALE_DAYS}d)", "warn"),
        card(len(buckets["open_all"]), "Open total", ""),
    ]
    if not baseline:
        cards.insert(3, card(len(buckets["reassigned"]), "Reassigned", ""))

    sections = []
    sections.append('<h2>Forward progress</h2>' + rows_transition(buckets["progressed"]))
    if buckets["regressed"]:
        sections.append('<h2>Moved backward</h2>' + rows_transition(buckets["regressed"]))
    sections.append('<h2>New intake</h2>' + rows_basic(buckets["created"]))
    sections.append('<h2>Per-person load</h2>' + load_rows(table))
    sections.append(f'<h2>Stalled / aging (open &ge;{STALE_DAYS}d, oldest first)</h2>'
                    + rows_basic(stalled, "Idle", "idle_days"))
    if not baseline:
        sections.append('<h2>Completed</h2>' + rows_basic(buckets["completed"]))
        if buckets["reassigned"]:
            sections.append('<h2>Reassigned</h2>' + rows_reassign(buckets["reassigned"]))
        if buckets["reopened"]:
            sections.append('<h2>Reopened</h2>' + rows_basic(buckets["reopened"]))

    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Jira Weekly Movement — {esc(ref.isoformat())}</title><style>{CSS}</style></head>
<body><div class="wrap">
<h1>Tech Team Jira — Weekly Movement</h1>
<div class="sub">{mode} &nbsp;|&nbsp; {title_range} &nbsp;|&nbsp; Projects: {esc(', '.join(projects))}</div>
<div class="cards">{''.join(cards)}</div>
{''.join(sections)}
<div class="foot">Generated {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')} from compact Jira snapshots. Forward progress, stalled/aging, and intake+load emphasized per configuration.</div>
</div></body></html>"""

# ---------- main ----------

def latest_snaps():
    files = sorted(glob.glob(os.path.join(SNAP_DIR, "*.json")))
    return files

def main():
    os.makedirs(REP_DIR, exist_ok=True)
    args = [a for a in sys.argv[1:]]
    baseline = False
    if args and args[0] == "--baseline":
        cur = load(args[1]); prev = None; baseline = True
    elif len(args) == 2:
        prev, cur = load(args[0]), load(args[1])
    else:
        files = latest_snaps()
        if not files:
            print("No snapshots found."); sys.exit(1)
        if len(files) == 1:
            cur = load(files[-1]); prev = None; baseline = True
        else:
            prev, cur = load(files[-2]), load(files[-1])

    if baseline:
        buckets, ref = baseline_buckets(cur)
        html_out = build_html(buckets, ref, None, cur.get("projects", []), baseline=True)
    else:
        buckets, ref = compute(prev, cur)
        html_out = build_html(buckets, ref, prev["captured_at"][:10],
                              cur.get("projects", []), baseline=False)

    out = os.path.join(REP_DIR, f"week-{cur['captured_at'][:10]}.html")
    with open(out, "w") as f:
        f.write(html_out)
    print(f"Report written: {out}")
    print(f"open={len(buckets['open_all'])} created={len(buckets['created'])} "
          f"progressed={len(buckets['progressed'])} completed={len(buckets['completed'])} "
          f"stalled={len(buckets['stalled'])}")

if __name__ == "__main__":
    main()

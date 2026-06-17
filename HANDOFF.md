# Tech Team Jira Handoff (TTD + NA)

_As of the weekly report dated 2026-06-15. Covers two things: (1) the current state of the work, and (2) how the weekly movement report is produced so you can keep running it._

---

## Part 1 — Current work status

### Scorecard (this week, TTD + NA only)

| Metric | Count |
|---|---|
| Open | 208 |
| Created this week | 9 |
| Progressed this week | 6 |
| Completed this week | 6 |
| Stalled | 133 |

Open splits 133 TTD / 75 NA. Of the 208 open items, only 32 are actually In Progress; the other 176 sit in To-Do-category statuses. Roughly 121 open items have not moved in 30+ days and 88 have not moved in 90+ days, so the backlog is large and mostly idle.

### Who owns the open work

The single largest "owner" of open work is nobody: **101 of 208 open items are Unassigned**. Among items with a real owner:

| Owner | Open items |
|---|---|
| Kyler Nelson | 29 |
| Cristobal Aguirre | 24 |
| Barry King | 22 |
| Bong Lee | 13 |
| Jeff Liang | 9 |
| Michael Dubay | 4 |
| Shyam Menon | 3 |
| Kassidy Stoffel | 1 |
| Jordan Serna | 1 |

The incoming owner's first job is triage of the 101 unassigned tickets, not net-new work.

### Completed this week

NA-248 (Back Order Split Line script timing, Cristobal Aguirre), NA-249 (ALA Last Quantity Issue, Jeff Liang), NA-273 (Tax exemption files for CS, Kyler Nelson), TTD-216 (Auto PO automation, Jeff Liang), TTD-267 (Customer Order History, Bong Lee), TTD-240 (EIM stock reduction/increase logic for Washburn and Columbus, Bong Lee), TTD-280 (Incorrect Expected Ship Date on Shopify Orders, Bong Lee), TTD-290 (Shipment Reconciliation Update, Barry King).

The clear theme is the warehouse routing / Columbus-Washburn workstream landing several items at once.

### In flight (progressed this week)

NA-251 FedEx Dallas Account (Ready For Dev → In Development, Cristobal Aguirre); TTD-73 EIM National Account Sales Capture (→ In Progress, Bong Lee); TTD-264 Incorrect Tax Rate for Unvalidated Address (In Progress → IN UAT, Barry King); TTD-286 Custom Print Picking Ticket Page (→ In Progress, Bong Lee); plus Barry King's TrackPOD cluster TTD-151, TTD-226, TTD-246.

### Stalled items and risk (read this first)

These are the items most likely to fall through the cracks during transition:

- **NA-76 "Scope out the process for Shopify"** is still assigned to a departed teammate ("Former user") and has been idle 143 days. Reassign or close.
- **Cristobal Aguirre is holding the five oldest open tickets overall** and none have moved in 8 months: NA-13 (245 days), NA-17, NA-18, NA-19 (238 days each), NA-7 (237 days). These are mostly credential/import documentation tasks. Decide if they are still real or should be closed.
- **Unassigned backlog (101 items)** is the bulk of the stalled count. A large block of TTD tickets (TTD-7 through roughly TTD-187, plus the TTD-21x/22x/23x range) has been untouched for ~88 to ~98 days with no owner.

### Suggested first actions for the incoming owner

1. Reassign or close NA-76 (departed user).
2. Review Cristobal's five 8-month-old NA tickets and either revive or close them.
3. Triage the 101 unassigned tickets into "real and prioritized" vs "stale, close it." This alone will cut the stalled count dramatically.
4. Keep the warehouse routing momentum: NA-272 (eBay DC region normalization) is a well-specified, high-value next build and references the just-completed Columbus work.

---

## Part 2 — How the weekly report works

### What it produces

Every run captures a compact snapshot of all open TTD + NA issues (plus recently completed ones), diffs it against the prior week's snapshot, and generates a self-contained HTML report showing what was created, progressed, completed, and what is stalling.

### Folder layout

Home: `MCP Servers/Jira Work Tracking & Reporting/` (full path
`/Users/adampaquette/Toolup Dropbox/Adam Paquette/MCP Servers/Jira Work Tracking & Reporting/`).
Everything below is relative to that folder root.

- `snapshots/` — one compact JSON per run, named `YYYY-MM-DD.json`. These are the source of truth for the diff. Keep them; they are how week-over-week movement is calculated.
- `reports/` — generated HTML, named `week-YYYY-MM-DD.html`. The deliverable.
- `Department Reports/<Dept>/` — the stakeholder-facing per-department reports (`group_report.py`).
- `diff_report.py` — the deterministic differ and HTML generator. **Do not modify it.** It reads the two most recent snapshots and writes the report.
- `README.md` — system overview. `HANDOFF.md` (this document) — Part 2 below is the weekly-run runbook.

### The run, step by step

1. Get today's date.
2. Look in `snapshots/`. If it is empty, it is a first/baseline run. If prior snapshots exist, it is a delta run and the most recent prior snapshot is the comparison point.
3. **Baseline:** page through every open TTD and NA issue plus anything completed in the last 10 days, and write the full compact list to `snapshots/TODAY.json`.
4. **Delta (normal weekly case):** read the prior snapshot, pull only what changed since then (`project in (TTD, NA) AND updated >= "PRIOR"`), merge those changes over the prior records, and write the merged set to `snapshots/TODAY.json`. Items that completed this week arrive in the delta marked Done and are kept so the differ can flag them.
5. Run the generator: it auto-selects the two latest snapshots and writes `reports/week-TODAY.html`, printing a one-line scorecard.
6. Present the report and post a short summary (scorecard, best progress, worst stalled items).

### Key constants

- Jira MCP search tool: `searchJiraIssuesUsingJql`
- cloudId: `e45ae1ec-ee36-4aee-94fc-3404ac60cb0d`
- Projects in scope: TTD and NA
- Page size: keep `maxResults` at 12. Larger pages exceed the tool's response size cap. Always follow the page token until there are no more pages.
- Compact fields stored per issue: key, summary, status, status category, assignee (or "Unassigned"), type, created, updated, due, url. Never store avatar URLs or raw Jira objects; that is what keeps the snapshots small.

### Running it manually

From this folder:

```
python3 diff_report.py                 # diff the two latest snapshots
python3 diff_report.py PREV.json CUR.json   # diff two specific snapshots
python3 diff_report.py --baseline CUR.json  # single-snapshot baseline report
```

The script prints the report path and a summary line in the form `open=.. created=.. progressed=.. completed=.. stalled=..`.

### Gotchas worth knowing

- **A third project, TDDE, now appears inside the snapshot files** (about 39-40 issues). The weekly report's scorecard is scoped to TTD + NA only, so the headline "open = 208" already excludes TDDE. If you compute numbers directly off a snapshot file, filter to TTD and NA or your totals will not match the report.
- **The snapshot files can be touched outside the weekly run.** A live dashboard artifact (id `jira-live-dashboard`) reads fresh data on open, and file modification times will not always line up with the weekly run. Treat the dated snapshot content, not the file timestamp, as authoritative.
- **Idempotency:** if a snapshot for today already exists, you do not need to re-pull. Re-running the generator over the existing snapshots reproduces the same report safely.
- **If the Jira MCP is unavailable, write no snapshot.** Do not fabricate data. Report that the pull failed and skip the week cleanly, so a partial week never pollutes the diff history.

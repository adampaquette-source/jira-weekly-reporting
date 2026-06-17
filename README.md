# Weekly Jira Movement Report

Automated weekly snapshot + diff of the tech-team Jira projects, rendered as a visual
HTML report. Configured for **TTD + NA + TDDE** (TDDE = Domo Data Engineering, added 2026-06-16),
running **Mondays ~9:30 AM** local.

## How it works

1. **Scheduled task** `weekly-jira-movement-report` (Cowork → Scheduled) runs each Monday.
2. It pulls current state from Jira (TTD + NA) and writes a compact JSON **snapshot** to
   `snapshots/YYYY-MM-DD.json`. Snapshots hold only the fields needed for diffing (no avatar
   URLs / raw Jira objects), so they stay a few KB.
   - **First run** builds a full baseline (open universe + items completed in the last 10 days).
   - **Later runs** pull only what changed since the prior snapshot and merge it forward, so
     the weekly pull stays cheap while the full open universe stays accurate.
3. `diff_report.py` compares the two latest snapshots and writes `reports/week-YYYY-MM-DD.html`.
   The diff logic is deterministic Python (not LLM-judged) so results are reproducible.

## The report

Emphasis (per configuration): **forward progress**, **stalled / aging**, and **new intake +
per-person load**. It also shows completions, reassignments, and reopens.

- Scorecard: new / progressed / completed / reassigned / stalled / open total.
- Forward progress: status transitions shown as `from → to`.
- New intake (created this week) and per-person open load.
- Stalled / aging: open items untouched ≥ 21 days, oldest first (this is where departed-user
  and zombie tickets surface).

## Timeline

- **Week 1 (first Monday):** establishes the baseline and produces a baseline report
  (load + stalled + intake; no transitions yet, since there's no prior week).
- **Week 2 onward:** full movement diffs, including precise `from → to` transitions.

## Files

- `diff_report.py` — the generator. Do not modify casually. Run manually with:
  `python3 diff_report.py` (auto two latest) or `python3 diff_report.py PREV.json CUR.json`
  or `python3 diff_report.py --baseline CUR.json`.
- `snapshots/` — weekly compact JSON state. Keep these; they are the diff history.
- `reports/` — generated HTML, one per week. `reports/_samples/` holds illustrative samples
  built from representative (not live) data so you can see the format.

## Companion: per-department (cross-functional group) reports

`group_report.py` turns the same snapshots into a **stakeholder-facing** summary for one
consuming department (Sales, Accounting, etc.), to send to that group's leader. Plain
language, outcome-first, grouped into **Shipped / In flight / New / Up next / Aging**.

Run: `python3 group_report.py Sales`. It writes **two** files into the
**`Department Reports/<Department>/`** subfolder (separate from
`reports/`, which holds the internal movement reports):
- `sales-YYYY-MM-DD.html` — rich browser view (has a `<style>` block).
- `sales-YYYY-MM-DD.email.html` — **email body**: inline styles only, no `<style>`/`<head>`,
  so it survives Gmail/Outlook (which strip embedded `<style>`). This is what the distribution
  Apps Script embeds and sends — see `distribution/`.

Aging hygiene: the "confirm or drop" section hides **unassigned** queued items idle more than
`DROP_UNASSIGNED_AGING_DAYS` (60) — likely-dead backlog — and shows the hidden count instead of
the rows. Tune in `group_report.py`.

It layers three things over the weekly diff:

1. **`dept-map.json`** — resolves each issue → department(s). Jira has department **labels**
   (`Sales`, `Accounting`, `Supply_Chain`, `Ecommerce`, `Operations`, `Technology`), but
   labels do **not** inherit to sub-tasks, so the map also supports `epic_to_dept` (parent/epic
   key → dept, children inherit), `key_overrides`, and `project_to_dept` (whole-project routing
   by key prefix — e.g. `TDDE` → `Domo`, so all Domo Data-Engineering tickets form a dedicated
   **Domo** report that goes to its owners Craig + Adam, instead of scattering ~40 finance/HR
   dashboard tickets across Supply Chain/Ecommerce). This is a **local** config Adam maintains —
   no Jira changes or team action needed. Correct it once when a report mis-buckets something.
   Example caught only by the map: TTD-267 (Customer Order History) is unlabeled but is a child
   of the Order Entry milestone TTD-94, so it surfaces as Sales work.
2. **`comments/YYYY-MM-DD.json`** — plain-English status notes, one per in-flight card. These
   are summarized by the pull-time agent from each card's **latest Jira comment** (markup and
   scheduling chatter stripped; bot/automation authors labeled as such). This is the "human
   layer" — captured on the card itself (the team was asked to comment on their cards), which
   **supersedes the Confluence-page approach** in `weekly-synthesis-plan.md`. Notes older than
   14 days are flagged "may be stale"; missing notes degrade gracefully.
3. The deterministic **movement diff** (from `diff_report.compute`) — completions, new intake,
   and `from → to` transitions, intersected with the department's membership.

**Report structure** (per the dev lead's ask): a short LLM-curated **Executive summary**
(top 2-5 callouts, authored weekly in `exec/<date>.json` — no sub-headings; falls back to a
one-line auto summary if absent), then sections in this order:
`Dev — Shipped + In Flight` · `Dev — New Requests` · `Dev — Next Sprint` · `Admin — pending
tagging` · `Domo / BI` · `Backlog`. The standalone Domo report drops the `Dev —` prefix and the
Admin/Domo sub-sections.

- **Next Sprint** uses Jira sprint membership. The connector can't read the Sprint field per
  issue, so the weekly pull tags `sprint: true` on snapshot items returned by
  `sprint in openSprints() OR sprint in futureSprints()`. "Next Sprint" = sprint-committed work
  not yet started; **Backlog** = open items not in a sprint (replaces the old Up-next/Aging
  split). NA has no sprints.
- "In flight" vs queued is decided by **workflow stage** (status name), not status category,
  because this Jira's QA/UAT statuses sit in the "To Do" category after a 2026-03 migration.

The Admin and Domo sections are kept **out of the executive summary's framing** and are appended:
- **🗄️ Admin — pending tagging** — high-confidence NetSuite-admin (NA) tickets recommended for
  this department (`admin_recommendations` in dept-map) but not yet labeled in Jira. They graduate
  into the main flow once the admin team applies the label.
- **📊 Domo / BI** — Domo (TDDE) dashboards/feeds related to this department (`domo_subdept`).
  Every TDDE item also appears in the standalone **Domo** report (which itself shows no
  Admin/Domo sub-sections).

### Snapshot schema note
Snapshots now also carry `labels` (list) and `parent` (parent/epic key or null) per issue, so
group membership and movement are reconstructable from history. The weekly pull should include
the Jira fields `labels` and `parent` and store `parent` as the parent key string (or null).
Older snapshots without these fields still diff fine (extra fields are optional).

## Companion: live dashboard

A Cowork artifact (`jira-live-dashboard`) shows the **current** state live (active WIP,
per-person WIP load, new-this-week, stalled) by querying Jira on open. The weekly HTML report
is the source of truth for **movement over time**; the artifact is the always-fresh snapshot.

## Tuning

- Stalled threshold: `STALE_DAYS` in `diff_report.py` (default 21).
- Add/remove projects: edit the JQL project lists in the weekly-run runbook
  (`HANDOFF.md` Part 2, in this folder) and the artifact HTML.
- Cadence: edit the scheduled task's cron (currently `30 9 * * 1`).

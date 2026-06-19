# ROUTINE — Weekly Jira reporting (cloud runbook)

This is the self-contained runbook a **claude.ai cloud routine** executes every Monday. The routine's
prompt is just: _"Execute the weekly Jira reporting run exactly as specified in ROUTINE.md at the repo
root. Treat today as the run date."_ Everything needed is below. Do not reference any prior chat.

## Environment & assumptions
- You run as a Claude Code cloud session with this repo cloned at the working directory.
- `python3` (stdlib only) is available. The engine: `diff_report.py`, `group_report.py`, `dept-map.json`.
- Connectors available (claude.ai account connectors, routed through Anthropic): **Jira/Atlassian**
  and **Gmail**. No local Dropbox/Drive access — this repo is the only persistent store.
- State lives in the repo: `snapshots/`, `comments/`, `exec/`, `reports/`, `Department Reports/`.
  At the end you **commit new state back** so next week's clone has it.

## Constants
- Jira cloudId: `e45ae1ec-ee36-4aee-94fc-3404ac60cb0d` (site `professionalcontractorsupply`).
- Projects: **TTD**, **NA**, **TDDE**. Departments to generate: Sales, Accounting, Supply Chain, Ecommerce, Operations, Domo.
- Email recipients + subjects:

  | Dept | To | Cc | Subject |
  |---|---|---|---|
  | Sales | brett.wilson@pcstools.com | bettyjean.dyer@pcstools.com, shawn.ledbetter@pcstools.com | IT Work for Sales — week of {date} |
  | Accounting | ryan.bednarz@pcstools.com | kayla.baca@pcstools.com | IT Work for Accounting — week of {date} |
  | Supply Chain | craig.weber@pcstools.com | warren.brown@pcstools.com | IT Work for Supply Chain — week of {date} |
  | Ecommerce | adam.paquette@pcstools.com | nickb@toolup.com | IT Work for Ecommerce — week of {date} |
  | Operations | michael.gambino@pcstools.com | brandon.show@pcstools.com | IT Work for Operations — week of {date} |
  | Domo | craig.weber@pcstools.com, adam.paquette@pcstools.com | — | Domo / BI Work — week of {date} |

## Steps

### 1. Date
Determine today's date `YYYY-MM-DD` → call it `{date}`.

### 2. Pull Jira → write `snapshots/{date}.json`
Use the Jira/Atlassian MCP search tool (`searchJiraIssuesUsingJql`) on the cloudId above.
- **Open universe:** `project in (TTD, NA, TDDE) AND statusCategory != Done` — page through ALL results
  (`maxResults` 12; follow the next-page token until exhausted; large responses otherwise overflow).
- **Recently completed:** also pull `project in (TTD, NA, TDDE) AND statusCategory = Done AND updated >= -10d`
  so completions show in the diff.
- **Sprint tagging:** separately run `project in (TTD, NA, TDDE) AND (sprint in openSprints() OR sprint in futureSprints())`
  and collect those keys; set `sprint: true` on matching issues, else `false`. (The connector can't read the
  Sprint field directly — this JQL is how sprint membership is derived.) NA is kanban (no sprints).
- **Build the snapshot** matching the EXACT schema of the existing `snapshots/` files (read the most recent
  one as a template). Per issue store only: `key, summary, status, cat` (status **category**), `assignee`
  (the display name, or the literal string `"Unassigned"` when none — never null, or the diff breaks),
  `type, created` (date), `updated` (date), `due` (or null), `url, labels` (list), `parent` (parent/epic key
  string or null), `sprint` (bool). Top level: `{"captured_at": "<ISO datetime>", "projects": ["TTD","NA","TDDE"], "issues": [...]}`.
  Never store avatar URLs or raw Jira objects. Write to `snapshots/{date}.json`.
- **If the Jira pull fails, STOP — do not fabricate data and do not write a partial snapshot.** Report the failure.

### 3. Author the LLM inputs (match the schema of the existing files in `comments/` and `exec/`)
- `comments/{date}.json` — for each card that is **in flight** (actively being built or in QA/UAT), summarize its
  **latest Jira comment** into a plain-English status note. Strip @-mentions and scheduling chatter; label bot/automation
  authors as such; if a comment's date is >14 days old it will be auto-flagged stale by the generator (just record the date).
- `exec/{date}.json` — per department, the top **2–5** callouts by importance (plain bullets). Falls back to an auto
  one-liner if a dept is missing.

### 4. Generate reports
```
python3 diff_report.py                         # → reports/week-{date}.html (movement report)
for d in Sales Accounting "Supply Chain" Ecommerce Operations Domo; do python3 group_report.py "$d"; done
```
Each dept run writes `Department Reports/<Dept>/<slug>-{date}.html` and `<slug>-{date}.email.html`.

### 5. Create 6 Gmail drafts (review queue — DO NOT SEND)
For each department, create a Gmail draft via the connector:
- `to` / `cc` / `subject` per the table (subject `{date}` = today).
- `htmlBody` = the **full contents** of that dept's `Department Reports/<Dept>/<slug>-{date}.email.html`
  (inline-styled email body — never the `.html` view).
- `body` (plain-text fallback) = a one-line summary, e.g. `This week for <Dept>: <counts>. (View as HTML for the full report.) — Adam Paquette, interim IT PM`.
- **Never send.** Drafts only — Adam reviews and sends manually.

### 6. Commit state back — MUST land on `main`
This is what makes the week-over-week diff advance. Each run clones `main` fresh, so this run's snapshot
must be committed to `main` or next week will keep diffing against the old seed snapshot and never move forward.
```
git add snapshots/ comments/ exec/ reports/ "Department Reports/"
git commit -m "Weekly run {date}"
git push origin HEAD:main          # push directly to main (unrestricted push is enabled for this repo)
```
Verify the push to `main` succeeded. If it is rejected, do NOT silently fall back to a `claude/` branch and
move on — instead report it loudly in the summary as a BLOCKER, because the running diff will stall until the
new snapshot reaches `main`.

### 7. Summary
Print: snapshot counts (open/created/progressed/completed/stalled from `diff_report.py`'s stdout), the 6 draft IDs
created, and anything that needed attention (e.g. departed-user assignees like NA-76, stale notes).

## Gotchas (read before changing anything)
- **`"Unassigned"` literal** for null assignees — storing null produces ~100 false reassignments in the diff.
- **Sprint** is JQL-derived (step 2), not a readable field.
- **Email = the `.email.html`** (inline styles); the `.html` view's `<style>` block is stripped by Gmail.
- **Paginate** the Jira pull with small `maxResults`; never assume one page.
- **Don't fabricate** on Jira failure — skip the week cleanly so a partial run never pollutes the diff history.
- The per-dept reports already carry the **AI-disclosure banner** (generated by `group_report.py`); don't remove it.

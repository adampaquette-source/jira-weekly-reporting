# Cloud routine setup (one-time, ~10 min)

Goal: run the weekly Jira pull + per-department reports **unattended in Anthropic's cloud** (laptop
closed), producing 6 Gmail drafts each Monday for you to review and send. The engine + history live
in a GitHub repo the routine clones each run; the routine commits new snapshots/reports back.

## Prerequisites (claude.ai account settings)
- A plan with **Claude Code on the web** enabled (Pro / Max / Team / Enterprise).
- **GitHub connected** to your claude.ai account (the routine clones a repo). Set up via `/web-setup`
  in a Claude Code CLI, or the GitHub App prompt during routine creation.
- **Jira (Atlassian) and Gmail connectors** connected on claude.ai (Settings → Connectors). These are
  what the routine uses; they're routed through Anthropic so they work in cloud runs.

## Step 1 — Publish this folder to GitHub (private) — ✅ DONE 2026-06-17
Published to **`git@github.com:adampaquette-source/jira-weekly-reporting`** (private). The local repo
tracks `origin/main`. Future changes: edit here, then `git add -A && git commit && git push`.

## Step 2 — Create the routine
Go to **https://claude.ai/code/routines → New routine** (or Desktop app → **Routines → New → Remote**).

- **Name:** `Weekly Jira reporting`
- **Prompt** (paste verbatim):

  > Execute the weekly Jira reporting run exactly as specified in `ROUTINE.md` at the repo root.
  > Treat today as the run date. Follow every step including building the snapshot, authoring the
  > comment/exec inputs, running the Python generators, creating the 6 Gmail drafts (drafts only —
  > never send), and committing the new state back to the repo. If the Jira pull fails, stop and
  > report — do not fabricate data.

  Pick a capable model in the prompt's model selector (Opus or Sonnet).
- **Repositories:** select the `jira-weekly-reporting` repo you just pushed.
- **Environment:** **Default** (Trusted) is fine — Python is stdlib-only and connector traffic is
  routed through Anthropic, so no custom network access is needed.
- **Connectors:** keep **Atlassian/Jira** and **Gmail**; remove any others you don't need.
- **Permissions:** enable **Allow unrestricted branch pushes** for this repo, so the routine can commit
  the weekly snapshot/reports to `main`. (If you'd rather not, it will push to a `claude/weekly-<date>`
  branch instead — but then continuity needs a manual merge; unrestricted push is simpler.)
- **Trigger:** **Schedule → Weekly → Monday**, time ~**9:33 AM** your local zone. (To set an exact cron,
  run `/schedule update` in the CLI and use `33 9 * * 1`.)
- Click **Create**.

## Step 3 — Test it
On the routine's detail page click **Run now**. Open the run session and confirm:
- `snapshots/<date>.json` written; `reports/week-<date>.html` + 6 `Department Reports/<Dept>/*.email.html` generated.
- **6 Gmail drafts** appear in your inbox (Sales, Accounting, Supply Chain, Ecommerce, Operations, Domo)
  with the AI-disclosure banner.
- A `Weekly run <date>` commit pushed to the repo.

A green run status only means the session didn't error — open the run to confirm the drafts actually
appeared. Then review the drafts in Gmail and send manually.

## Managing it
- **Edit** prompt/connectors/schedule: pencil icon on the routine, or `/schedule update` in the CLI.
- **Pause/resume:** the toggle in the routine's **Repeats** section.
- **Change what's in the report:** edit `ROUTINE.md` or `dept-map.json` in the repo and push — the next
  run picks it up (the routine clones fresh each time).
- Runs count against your account's daily routine allowance + normal subscription usage.

## Notes
- The current Drive-based `distribution/` Apps Script (auto-SEND) remains the **separate later phase**;
  this routine stops at **drafts** per your "I'll send manually" preference.
- Source of truth for the automated path is now the **GitHub repo**. Keep editing config there (or here
  then push). The Dropbox copy is your local working copy.

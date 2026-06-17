# Distribution — emailing the per-department reports

Goal (at maturity): each department report goes out as a **scheduled email from Adam's inbox**,
with the report **in the email body** (not an attachment), drafted first for review then sent.

## The two halves

1. **Local generator** (`../group_report.py`) writes two files per run into
   `Department Reports/<Dept>/`:
   - `<slug>-<date>.html` — rich browser view (has a `<style>` block).
   - `<slug>-<date>.email.html` — **email body**: inline styles only, no `<style>`/`<head>`,
     because Gmail (in some views) and Outlook strip embedded `<style>`. This is the file the
     Apps Script embeds.
2. **Apps Script** (`send_department_reports.gs`) runs in Adam's Google account, reads the
   latest `*.email.html` per department from a Drive folder, and drafts/sends the email.

Apps Script can't read the local Dropbox folder, so Drive is the bridge.

### Drive folder (wired)

- **Name:** `IT Department Reports`
- **Folder ID:** `1CHwX0WCFn8HxoHwbcU5j9s88lwd7vFVd`  ← already set in `send_department_reports.gs`
- **URL:** https://drive.google.com/drive/folders/1CHwX0WCFn8HxoHwbcU5j9s88lwd7vFVd
- Owner: adam.paquette@pcstools.com

## Getting the `.email.html` into Drive

The **Drive connector is wired**: after each generation, Claude uploads the week's
`<slug>-<date>.email.html` into the folder above (as `text/html`, no Google-Docs conversion).
This is part of the weekly task — no manual step. The first Sales upload
(`sales-2026-06-15.email.html`) is already in the folder.

Fallbacks if the connector isn't available: drag the file into the folder by hand, or keep the
files in a Drive-for-Desktop–synced location. Only `*.email.html` files matter; `.html` view
files are ignored by the script (it matches `*.email.html` only).

## One-time setup

1. ~~Create a Drive folder~~ — **done.** Folder `IT Department Reports`
   (`1CHwX0WCFn8HxoHwbcU5j9s88lwd7vFVd`) is created and already set as `driveFolderId`.
2. https://script.google.com → **New project** → paste in `send_department_reports.gs`.
3. Edit the `CONFIG` block:
   - `departments` — for each dept, the real recipient(s), optional cc, and subject template.
     Keys must match the department name used by the generator (`Sales`, `Supply Chain`, …).
     **(This is the only thing left to fill in before the first send.)**
   - `fromName` (and `sendAsAddress` if you send from an alias).
4. Run `draftDepartmentReports` once; approve the Gmail/Drive authorization prompt.

## Weekly use

- **Review-then-send (recommended to start):**
  1. Run `draftDepartmentReports()` → one Gmail **draft** per department (sends nothing).
  2. Open the drafts in Gmail, skim, tweak wording if needed.
  3. Run `sendDraftedReports()` → sends exactly those drafts. (Or just hit Send in Gmail.)
- **Fully unattended:** `draftAndSend()` drafts and sends in one call.
- **Schedule it:** run `installWeeklyTrigger()` once to fire `draftDepartmentReports` every
  Monday ~10:00 (right after the Monday 9:30 Jira pull + report generation). Add a second
  time trigger for `sendDraftedReports` later in the day once you trust the output, or send by
  hand from your drafts.

## Notes / guardrails

- Drafting is always safe — it never sends. Sending is a separate, explicit step.
- The script picks the **newest** report per department by the date in the filename, so stale
  files in the folder won't go out.
- Missing report or empty recipient list = that department is skipped with a log line
  (`View → Logs`), the rest still go.
- `sendDraftedReports()` only sends drafts created by *today's* `draftDepartmentReports()` run,
  so re-running send won't resurrect old drafts.

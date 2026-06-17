/**
 * Department report distribution — Google Apps Script (Gmail + Drive).
 *
 * Flow (matches "send the reports after drafting"):
 *   1. group_report.py writes  <slug>-YYYY-MM-DD.email.html  (inline-styled email body).
 *   2. That file lands in a Drive folder (see README: Drive for Desktop, manual upload,
 *      or the Drive connector).
 *   3. draftDepartmentReports()  -> creates a Gmail DRAFT per department for you to review.
 *   4. You skim the drafts in Gmail. Then either hit send by hand, or run
 *      sendDraftedReports() -> sends exactly the drafts created in step 3 (tracked by id).
 *   5. At maturity: a time-driven trigger runs draftDepartmentReports() Monday ~10:00, and
 *      (optionally) sendDraftedReports() later that day once you trust it. draftAndSend()
 *      does both in one shot for a fully unattended schedule.
 *
 * Nothing sends without you choosing a send path — drafting is always safe to run.
 */

// ======================= CONFIG — edit these =======================
var CONFIG = {
  // Drive folder that holds the *.email.html report files.
  // "IT Department Reports" (created 2026-06-15, owner adam.paquette@pcstools.com).
  driveFolderId: '1CHwX0WCFn8HxoHwbcU5j9s88lwd7vFVd',

  // Optional "from" display name (must be an address/alias you can send as).
  fromName: 'Adam Paquette',
  // sendAsAddress: 'adam.paquette@pcstools.com',   // uncomment to force a specific alias

  // One entry per department you want to distribute. The key MUST match the department name
  // used by group_report.py / dept-map.json (the file slug = key lowercased, spaces -> dashes).
  // Fill each `to` with the real group lead(s). A department with no recipients is skipped
  // (logged), so you can roll out one at a time by filling them in as you go.
  departments: {
    'Sales': {
      to:   ['brett.wilson@pcstools.com'],          // <-- real recipient(s)
      cc:   ['bettyjean.dyer@pcstools.com', 'shawn.ledbetter@pcstools.com'],
      subjectTemplate: 'IT Work for Sales — week of {date}'
    },
    'Accounting': {
      to:   ['ryan.bednarz@pcstools.com'],
      cc:   ['kayla.baca@pcstools.com'],
      subjectTemplate: 'IT Work for Accounting — week of {date}'
    },
    'Supply Chain': {
      to:   ['craig.weber@pcstools.com'],
      cc:   ['warren.brown@pcstools.com'],
      subjectTemplate: 'IT Work for Supply Chain — week of {date}'
    },
    'Ecommerce': {
      to:   ['adam.paquette@pcstools.com'],      // note: Adam is the ecommerce stakeholder
      cc:   ['nickb@toolup.com'],
      subjectTemplate: 'IT Work for Ecommerce — week of {date}'
    },
    'Operations': {
      to:   ['michael.gambino@pcstools.com'],
      cc:   ['brandon.show@pcstools.com'],
      subjectTemplate: 'IT Work for Operations — week of {date}'
    },
    'Domo': {
      to:   ['craig.weber@pcstools.com', 'adam.paquette@pcstools.com'],  // Domo rolls up to Craig + Adam
      cc:   [],
      subjectTemplate: 'Domo / BI Work — week of {date}'
    },
    'Technology': {
      to:   [],   // usually internal — leave empty to skip, or add a recipient to distribute
      cc:   [],
      subjectTemplate: 'IT Work for Technology — week of {date}'
    },
    'Exec': {
      to:   [],   // optional exec roll-up — add recipient(s) to enable
      cc:   [],
      subjectTemplate: 'IT Work for Exec — week of {date}'
    }
  }
};
// ===================================================================

/** Create one Gmail draft per configured department (review step — sends nothing). */
function draftDepartmentReports() {
  var created = {};
  forEachDept_(function (dept, cfg, report) {
    var draft = GmailApp.createDraft(cfg.to.join(','), subject_(cfg, report.date), '', {
      htmlBody: report.html,
      cc: (cfg.cc || []).join(','),
      name: CONFIG.fromName
    });
    created[dept] = draft.getId();
    Logger.log('Drafted ' + dept + ' (' + report.fileName + ') -> draft ' + draft.getId());
  });
  // Remember which drafts belong to today's run so sendDraftedReports() can send them.
  PropertiesService.getScriptProperties()
    .setProperty('drafts:' + today_(), JSON.stringify(created));
  return created;
}

/** Send exactly the drafts created by the most recent draftDepartmentReports() run today. */
function sendDraftedReports() {
  var raw = PropertiesService.getScriptProperties().getProperty('drafts:' + today_());
  if (!raw) { Logger.log('No drafts recorded for ' + today_() + '. Run draftDepartmentReports() first.'); return; }
  var map = JSON.parse(raw), sent = 0;
  Object.keys(map).forEach(function (dept) {
    try {
      GmailApp.getDraft(map[dept]).send();
      sent++;
      Logger.log('Sent ' + dept);
    } catch (e) {
      Logger.log('Could not send ' + dept + ' (draft ' + map[dept] + '): ' + e);
    }
  });
  PropertiesService.getScriptProperties().deleteProperty('drafts:' + today_());
  Logger.log('Sent ' + sent + ' report(s).');
}

/** One-shot: draft + immediately send (for a fully unattended scheduled trigger). */
function draftAndSend() {
  draftDepartmentReports();
  sendDraftedReports();
}

// ----------------------- helpers -----------------------

function forEachDept_(fn) {
  var folder = DriveApp.getFolderById(CONFIG.driveFolderId);
  Object.keys(CONFIG.departments).forEach(function (dept) {
    var cfg = CONFIG.departments[dept];
    if (!cfg.to || !cfg.to.length) { Logger.log('Skip ' + dept + ': no recipients.'); return; }
    var report = latestReport_(folder, dept);
    if (!report) { Logger.log('Skip ' + dept + ': no *.email.html found in folder.'); return; }
    fn(dept, cfg, report);
  });
}

/** Find the newest <slug>-YYYY-MM-DD.email.html for a department, by the date in the name. */
function latestReport_(folder, dept) {
  var slug = dept.toLowerCase().replace(/\s+/g, '-');
  var re = new RegExp('^' + slug.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '-(\\d{4}-\\d{2}-\\d{2})\\.email\\.html$');
  var files = folder.getFiles(), best = null;
  while (files.hasNext()) {
    var f = files.next(), m = re.exec(f.getName());
    if (m && (!best || m[1] > best.date)) {
      best = { file: f, date: m[1], fileName: f.getName() };
    }
  }
  if (!best) return null;
  best.html = best.file.getBlob().getDataAsString('UTF-8');
  return best;
}

function subject_(cfg, dateStr) {
  return (cfg.subjectTemplate || 'IT Work — week of {date}').replace('{date}', dateStr);
}

function today_() {
  return Utilities.formatDate(new Date(), Session.getScriptTimeZone(), 'yyyy-MM-dd');
}

/** Run once to schedule weekly drafting (Mondays ~10:00). Edit/extend as needed. */
function installWeeklyTrigger() {
  ScriptApp.newTrigger('draftDepartmentReports')
    .timeBased().onWeekDay(ScriptApp.WeekDay.MONDAY).atHour(10).create();
  Logger.log('Installed Monday 10:00 trigger for draftDepartmentReports.');
}

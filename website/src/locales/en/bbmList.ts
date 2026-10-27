// The BBM list page (pages/BbmPage.tsx, controllers/BbmController.ts). The list's scope ("{{scope}}") is
// " (October 2026, every page)" or "".

const bbmList = {
  title: "BBM reimbursements",
  subtitle: "Fuel reimbursements sent by other systems, checked against what the OCR read on their receipt files.",
  month: {
    label: "Received in",
    all: "All months ({{count}})",
  },
  loading: "Loading the reports…",
  loadError: "Couldn't load the reports",
  search: {
    label: "Search by code, employee name or number",
    queue: "Search “{{text}}”",
  },
  allReports: "All reports",
  everyPage: "every page",
  range: {
    paged_one: "{{from}}–{{to}} of {{count}} report",
    paged_other: "{{from}}–{{to}} of {{count}} reports",
    pagedMatching_one: "{{from}}–{{to}} of {{count}} matching report",
    pagedMatching_other: "{{from}}–{{to}} of {{count}} matching reports",
    filtered_one: "{{shown}} of {{count}} report",
    filtered_other: "{{shown}} of {{count}} reports",
  },
  filters: {
    label: "Filter by status",
    receivedIn: "Received in {{month}}",
    every: "Every BBM report",
    parts: "{{status}}: which part",
  },
  partHints: {
    duplicate:
      "A report received earlier claims the same receipt as each of these: the same file, or the same employee's " +
      "receipt with the same day, amount and volume. Open the report to compare the two: reject it if the receipt is " +
      "claimed twice, approve it if they are different receipts.",
    proceed:
      "The OCR approved these because it judged every difference a misread. Spot-check them: if a difference is a " +
      "real mismatch, open the report and reject it.",
    failed:
      "Claude couldn't give a reading of these files (it timed out, couldn't run or gave no usable answer), so " +
      "nothing was compared: it says nothing about the receipt. Retry the OCR on all of them (or on one, from its " +
      "report), or check the file against the submitted data yourself.",
  },
  pages: "Report pages",
  table: {
    caption: "BBM reimbursement reports",
    report: "Report",
    employee: "Employee",
    received: "Received",
    total: "Total",
    differences: "What differs",
    status: "Status",
    open: "Open",
  },
  empty: {
    none: "No BBM reimbursements yet",
    noneText: "Other systems send them to the reimbursement API (POST /api/reimbursements).",
    month: "No reports received in {{month}}",
    monthText: "Choose another month, or show the reports of every month.",
    showAllMonths: "Show all months",
    noMatch: "No reports match",
    showAllOf: "Show all of {{month}}",
    showAll: "Show all reports",
  },
  noMatch: {
    search: "Nothing matches “{{text}}”.",
    searchIn: "Nothing matches “{{text}}” in {{where}}.",
    status: "No report has this status right now.",
    statusIn: "No report received in {{month}} has this status.",
  },
  report: {
    files: "{{count}} files",
    by: "By {{name}}",
    byOcrProceed: "By the OCR: misreads only",
    byOcrMatched: "By the OCR: matched",
    doubleClaim: "Receipt already claimed",
  },
  ocr: {
    label: "OCR:",
    processing: "OCR: processing",
    failed: "OCR: couldn't read",
    same: "OCR: same",
    less: "The OCR read {{amount}} less than submitted",
    more: "The OCR read {{amount}} more than submitted",
  },
  differences: {
    notYet: "Not compared yet",
    notCompared: "Not compared",
    none: "Nothing",
    count_one: "{{count}} difference in {{field}}",
    count_other: "{{count}} differences in {{field}}",
  },
  export: {
    button: "Export to Excel",
    exporting: "Exporting…",
    none: "No reports to export",
    hint_one:
      "Download the report in this list{{scope}} as an Excel file: one row per receipt, what was submitted next to " +
      "what the OCR read.",
    hint_other:
      "Download the {{count}} reports in this list{{scope}} as an Excel file: one row per receipt, what was submitted " +
      "next to what the OCR read.",
    tooMany: "Too many reports to export",
    tooManyText: "Export at most {{max}} at once. Choose a month or status to make the list shorter.",
    exported_one: "Exported {{count}} report",
    exported_other: "Exported {{count}} reports",
    changed: "The list changed since it was loaded (it showed {{shown}}). It is now refreshed. File: {{file}}",
    done_one: "Exported {{count}} report to Excel",
    done_other: "Exported {{count}} reports to Excel",
    nothing: "Nothing exported",
    nothingText: "These reports changed since the list was loaded. The list is now refreshed.",
    failed: "Couldn't export to Excel",
  },
  retry: {
    button: "Retry OCR",
    all: "Retry OCR on all {{count}}",
    retrying: "Retrying…",
    hint_one: "Retry the OCR on the report in this list{{scope}}",
    hint_other: "Retry the OCR on the {{count}} reports in this list{{scope}}",
    title: "Retry the OCR on {{code}}?",
    titleCount_one: "Retry the OCR on {{count}} report?",
    titleCount_other: "Retry the OCR on {{count}} reports?",
    text:
      "Its receipt file goes back in the OCR queue. Claude reads it again, usually in 15 to 35 seconds, and the " +
      "report shows as Processing until then.",
    textAll:
      "The receipt files of the {{count}} reports in this list{{scope}} go back in the OCR queue. Claude reads them " +
      "again one after the other, usually in 15 to 35 seconds a file, and the reports show as Processing until then.",
    stillFails: "If Claude still can't read a file, its report comes back to this list.",
    failed: "The OCR was not retried",
    queued_one: "Retrying the OCR on {{count}} report",
    queued_other: "Retrying the OCR on {{count}} reports",
    queuedText: "They are in Processing until the OCR has read them.",
    skipped_one: "{{count}} was retried or decided in the meantime and left as it is.",
    skipped_other: "{{count}} were retried or decided in the meantime and left as they are.",
    showProcessing: "Show processing",
    nothing: "Nothing to retry",
    nothingText: "{{error}} The list is now refreshed.",
  },
};

export default bbmList;

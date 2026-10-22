// The home page (pages/HomePage.tsx, controllers/HomeController.ts).

const home = {
  greeting: {
    morning: "Good morning, {{name}}",
    midday: "Good afternoon, {{name}}",
    afternoon: "Good afternoon, {{name}}",
    evening: "Good evening, {{name}}",
  },
  subtitle: "Check the reimbursements other systems send, with what the OCR read on each receipt file.",
  loadingReports: "Loading the reports…",
  loadError: "Couldn't load the reports",
  empty: {
    title: "No reimbursements yet",
    text: "Other systems send them to the reimbursement API (POST /api/reimbursements). They show up here once received.",
  },
  clear: {
    eyebrow: "All caught up",
    title: "No report needs review",
    processing_one: "The OCR is still reading {{count}} report. If one needs a reviewer, it shows up here.",
    processing_other: "The OCR is still reading {{count}} reports. If one needs a reviewer, it shows up here.",
    done: "Every report is approved or rejected: nothing is left to decide.",
  },
  attention: {
    eyebrow: "Needs your review",
    title_one: "report needs a reviewer",
    title_other: "reports need a reviewer",
    receivedIn: "Received in",
    chipTitle: "The reports received in {{month}} that need review",
    moreMonths_one: "+{{count}} more month",
    moreMonths_other: "+{{count}} more months",
    moreMonthsTitle: "Every report that needs review, oldest first",
    start: "Start reviewing",
    oldestFrom: "Oldest first, from {{code}}",
    seeList: "See them in a list",
  },
  bbm: {
    subtitle: "Fuel reimbursements",
    open: "Open BBM reports",
    loading: "Loading the BBM reports…",
    reports: "Reports",
    submitted: "Submitted",
    approved: "Approved",
    approvedAmount: "{{amount}} approved",
    of: " of {{total}}",
    byStatus: "Reports by status",
    byMonth: "By month received",
    thisMonth: "This month",
    olderMonths_one: "{{count}} older month:",
    olderMonths_other: "{{count}} older months:",
    pickOnList: "pick it on the BBM list",
  },
  month: {
    needReview_one: "{{count}} needs review",
    needReview_other: "{{count}} need review",
    processing: "{{count}} processing",
    clear: "Nothing to review",
  },
};

export default home;

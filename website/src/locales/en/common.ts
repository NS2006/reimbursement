// Texts shared by every page: the app, the navbar, the language switch, the review and OCR statuses, the BBM field
// names and the error messages. Plurals: key_one / key_other, picked by the count passed as { count }.

const common = {
  app: {
    name: "Reimbursement",
  },
  nav: {
    home: "Home",
    bbm: "BBM",
    fuelPrices: "Fuel prices",
  },
  title: {
    home: "Home",
    bbm: "BBM",
    fuelPrices: "Fuel prices",
    report: "{{code}} · BBM",
    notFound: "Page not found",
    signIn: "Sign in",
  },
  language: {
    label: "Language",
    en: "English",
    id: "Bahasa Indonesia",
  },
  user: {
    switch: "Switch user",
  },
  actions: {
    refresh: "Refresh",
    refreshing: "Refreshing…",
    tryAgain: "Try again",
    cancel: "Cancel",
    close: "Close",
  },
  updatedAt: "Updated {{time}}",
  reports_one: "{{count}} report",
  reports_other: "{{count}} reports",
  reviewStatus: {
    needs_review: {
      label: "Needs review",
      hint: "A reviewer must decide",
      meaning: "A reviewer must check the receipt file and approve or reject the report.",
    },
    processing: {
      label: "Processing",
      hint: "The OCR is reading it",
      meaning: "The OCR is reading the receipt file. It is compared with the submitted data as soon as it is read.",
    },
    approved: {
      label: "Approved",
      hint: "By the OCR or a reviewer",
      meaning: "Approved: the receipt agrees, the only differences are OCR misreads, or a reviewer approved it.",
    },
    rejected: {
      label: "Rejected",
      hint: "Refused by a reviewer",
      meaning: "A reviewer rejected the report. A corrected report can be sent again under a new code.",
    },
  },
  ocrStatus: {
    needs_review: {
      label: "Needs review",
      hint: "A reviewer must check the file",
      meaning: "A reviewer must check the receipt file: the OCR found a difference it cannot explain.",
    },
    failed: {
      label: "OCR couldn't read",
      hint: "A reviewer must check the file",
      meaning:
        "The OCR could not read the receipt file, so it was not compared: a reviewer must check it against the submitted data.",
    },
    processing: {
      label: "Processing",
      hint: "The OCR is reading it",
      meaning: "The OCR is reading the receipt file. It is compared with the submitted data as soon as it is read.",
    },
    proceed: {
      label: "Proceed",
      hint: "Differences are only OCR misreads",
      meaning:
        "The OCR found differences, but each one is an OCR misread: the other numbers on the receipt prove the submitted value.",
    },
    matched: {
      label: "Matched",
      hint: "The receipt agrees",
      meaning: "The receipt file agrees with the submitted data.",
    },
  },
  approvedBy: {
    matched: { label: "Matched", text: "By the OCR: the receipt matches" },
    proceed: { label: "Proceed", text: "By the OCR: only OCR misreads" },
    reviewer: { label: "By a reviewer", text: "By a reviewer" },
  },
  needsReviewReason: {
    duplicate: {
      label: "Possible double claim",
      text: "A report received earlier claims the same receipt (the same file, or the same day, amount and volume)",
    },
    differences: { label: "Differences", text: "The OCR read the receipt file and found differences it couldn't explain" },
    failed: { label: "OCR couldn't read", text: "The OCR couldn't read the receipt file, so nothing was compared" },
  },
  statusParts: {
    needs_review: { label: "All to review", text: "Every report that needs a reviewer" },
    approved: { label: "All approved", text: "Every approved report" },
  },
  statusBar: {
    empty: "No reports",
  },
  fields: {
    product_name: "Product",
    date_of_expense: "Date",
    price_per_liter: "Price per liter",
    volume_liter: "Volume (L)",
    kilometer: "Kilometer",
    total_price: "Amount",
    discount: "Discount",
    grand_total: "Grand total",
  },
  blue: {
    dismissAlert: "Dismiss alert",
    close: "Close",
    previousPage: "Previous page",
    nextPage: "Next page",
    pages: "Pages",
    mainNav: "Main",
    breadcrumb: "Breadcrumb",
    loading: "Loading",
    notifications: "Notifications",
    closeNotification: "Close notification",
    nothingToShow: "Nothing to show.",
    remove: "Remove",
  },
  errors: {
    unreachable: "Can't reach the server. Check your connection and try again.",
    generic: "Something went wrong. Please try again.",
    http: "The server answered with HTTP {{status}}.",
    invalidRequest: "The request was not valid. Reload the page and try again.",
    // By the backend's error code. In English the backend's own message is shown (it has the details); these are
    // used when it sent none.
    codes: {
      already_decided: "This report is already decided.",
      decided: "This report is already decided. Take the decision back to retry the OCR.",
      decision_changed: "Someone changed the decision on this report in the meantime. Check it before deciding.",
      empty_list: "There is no report in this list.",
      file_missing: "The file is not in the file storage.",
      file_storage_unavailable: "The file can't be read right now. Try again later.",
      internal_error: "Something went wrong on the server.",
      invalid_based_on: "The decisions on this report changed. Reload the page and try again.",
      invalid_description: "The comment is empty or too long.",
      invalid_list: "Only the list Needs review · OCR couldn't read can be retried at once.",
      invalid_q: "The search can have at most 100 characters.",
      invalid_reason: "The reason is too long.",
      invalid_user: "Unknown user. Pick another user.",
      not_comment_author: "You can only edit or delete your own comments.",
      not_found: "Not found.",
      nothing_failed: "The OCR is not stuck on this report any more: it was retried in the meantime.",
      nothing_to_reopen: "There is no decision on this report to take back.",
      reason_required: "Say why the report is rejected.",
      refresh_active: "A fuel price update is already queued or running.",
      refresh_too_soon: "The fuel prices were updated a moment ago. Try again later.",
      too_many_reports: "This list has more than 5,000 reports. Choose a month or narrow the search.",
    },
  },
};

export default common;

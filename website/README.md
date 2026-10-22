# Reimbursement website

Internal website to review the reimbursement data (comparison, CRUD). It is the frontend only; everything backend lives
in `../backend/`. Pages so far:

- `/` home: what needs the reviewer (the reports that need review, by month; "Start reviewing" opens the oldest and
  each decision opens the next one), and BBM at a glance (reports per review status and per month, each linking to the
  list).
- `/bbm` BBM (fuel) reports: a month picker ("Received in": all months or one month), a card per review status
  (needs review, processing, approved, rejected; click to filter; approved ones also by how: matched, proceed or
  by a reviewer, so the OCR's "proceed" approvals can be spot-checked), search by code or employee, sort by any column,
  20 reports per page; the month, filter, search, sort and page are kept in the URL. "Export to Excel" downloads the
  reports in the list (the chosen month, status and search, every page) as one sheet: a row per receipt, what was
  submitted next to what the OCR read, with the differences highlighted, the status and who decided it and why.
- `/bbm/<code>` one BBM report: a summary of what the OCR found and what to check, the receipt file next to it (a photo or a PDF, drawn page by page with pdf.js),
  the submitted items and what the OCR read in the same columns, what changed since the revision before (and why it
  was rejected), its history, and comments (edit and delete your own). The decision bar at the bottom approves or
  rejects the current revision (a reason is required to reject), or takes a decision back; a toast offers Undo. In the
  "Needs review" list, deciding opens the next report. Back, previous and next follow the list the report was opened from.

The login page is a **development user picker**: you choose a user from the `app_user` table, with no password.
Real sign-in will come from the Blibli gateway. The picked user is remembered in the browser (localStorage) until "Switch user".

Stack: React 19 + TypeScript + Vite 6, styled with the Blibli BLUE3 tokens and components (`src/components/blue/`).

## Run it (development)

Start the backend API from the repository root (needs PostgreSQL running and the `DB_*` settings in `.env`,
see the main README):

```bash
py -m backend.app
```

Then, from this folder:

```bash
npm install
npm run dev
```

Open http://localhost:5173. Vite forwards every `/api` call to the backend at http://127.0.0.1:5000.

Other commands: `npm run build` (type-check and production build) and `npm run lint`.

## Layout

```
website/
├── index.html
├── vite.config.ts        # dev server settings and the /api proxy
└── src/
    ├── main.tsx          # entry point
    ├── app/
    │   ├── App.tsx       # app shell: login page until a user is picked, then the page for the URL
    │   ├── i18n.ts       # the language (Indonesian or English, i18next): t(), setLanguage(), dateLocale()
    │   └── router.ts     # small router (no library): useLocation, navigate, linkTo
    ├── pages/            # route-level pages (LoginPage, HomePage, BbmPage, BbmReportPage, NotFoundPage)
    ├── layouts/          # page frames (AppLayout.tsx: BlueNavbar with the links, the language and the current user)
    ├── controllers/      # logic and data for the pages, one controller per page
    │   ├── api.ts        #   general helpers for calling the backend (request, requestFile, jsonBody, errors, useApi)
    │   ├── LoginController.ts  # login page: its backend calls, state and actions, plus the current user
    │   ├── HomeController.ts   # home: what needs review (the review queue), BBM per status and month
    │   ├── BbmController.ts    # BBM list: the reports, month, status filter, search, sort and page (kept in the URL), Excel export
    │   └── BbmReportController.ts  # one BBM report: shown revision, differences per cell, revision changes, decisions, history, comments
    ├── components/
    │   ├── blue/         # BLUE3 components (BlueButton, BlueNavbar, BlueTable, BluePagination, BlueTag, BlueModal, BlueToast, ...), imported file by file
    │   └── *.tsx         # app components built on them (CommentThread, OcrStatusBadge, ReviewStatusBadge, PhotoViewer, FileViewer, StatusBar, LanguageSwitch)
    ├── locales/          # the texts: en/ and id/, one file per area (common, home, login, bbmList, report, components)
    ├── styles/           # all CSS: BLUE3 tokens, global styles, and one file per component in the same
    │                     #   folders as the code (styles/pages/LoginPage.css belongs to pages/LoginPage.tsx)
    ├── types/            # shared types (User, reimbursements)
    └── utils/            # display helpers (format.ts: rupiah, numbers, dates; ocrStatus.ts / reviewStatus.ts: status labels; bbmFields.ts: BBM field names; download.ts: save a file; pdfPages.ts: draw PDF pages)
```

A new navbar link is one entry in `navItems()`, and a new page one case in `routeOf()` and in `Page`, all in `src/app/App.tsx`.

## Languages

The website is in Indonesian (the default) or English; the ID | EN switch in the navbar (and on the login page)
is remembered in the browser. Every text is in `src/locales/<language>/<area>.ts` and read with `t()` from
`src/app/i18n.ts`, e.g. `t("home:attention.start")` or `t("reports", { count })` (plurals: `key_one` / `key_other`).
A new text goes in the English file first (its keys are the ones `t()` accepts, so a typo does not build) and
then in the Indonesian one (it must have the same keys).

- Technical words stay English in both: Reimbursement, OCR, BBM, Reviewer, Grand total, Proceed, Excel, PDF.
- Amounts and numbers are Indonesian style (Rp 1.234.567) and dates DD-MM-YYYY in both; month and day names follow
  the language.
- The backend's error messages are English. In Indonesian the website shows its own text for the error code
  (`errors.codes` in `common.ts`).
- The Excel export stays English (it is made by the backend).

New pages follow the same split: the page (JSX only) in `src/pages/<Name>Page.tsx`, its logic and its
backend calls in `src/controllers/<Name>Controller.ts` (using `request()` from `api.ts`), and its CSS in
`src/styles/pages/<Name>Page.css`.

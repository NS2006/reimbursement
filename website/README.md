# Website

The review website: reviewers check the reimbursement reports that the OCR couldn't approve, spot-check the ones it
did, and approve or reject them. It's the frontend only; the data comes from the API in [../backend/](../backend/).

React 19 + TypeScript + Vite 6, styled with Blibli's BLUE3 design system, in Indonesian (default) or English.

```bash
npm install
npm run dev        # http://localhost:5173 (the API must run on http://127.0.0.1:5000, see below)
npm run build      # type-check and production build into dist/
npm run lint
```

Start the API first, from the repository root: `py -m backend.app` (setup in the [main README](../README.md)).
In development Vite forwards every `/api` call to it ([vite.config.ts](vite.config.ts)); in Docker nginx does.

---

## Pages

| Path | Page |
|---|---|
| `/` | **Beranda (Home).** How many reports need review and in which months. **Mulai review** opens the oldest, and each decision moves on to the next. Also BBM at a glance: reports per status and per month. |
| `/bbm` | **The BBM list.** A month picker, a card per review status (approved ones also split into matched, proceed and approved by a reviewer, to spot-check the OCR), search, sort by any column, 20 per page. The month, filter, search, sort and page live in the URL. **Ekspor ke Excel** downloads the whole list. |
| `/bbm/<code>` | **One report.** What the OCR found and what to check, the receipt file (photo or PDF) next to the submitted items and what the OCR read, with each difference marked. Also what changed since the previous revision, the history and comments. The bar at the bottom approves or rejects (rejecting needs a reason) or takes a decision back; previous and next follow the list the report was opened from. |

**Sign-in:** for now the login page is a development user picker (users from the `app_user` table, no password),
remembered in the browser until **Ganti pengguna**. Real sign-in will come from the Blibli gateway.

**Months:** a report belongs to the month it was received in, **in WIB** for every reviewer (as the backend). The
list and the report page show only that month, not the day: Darwinbox sends reports in weekly batches, so the day
they arrive says little.

---

## Layout

```
src/
├── main.tsx              # entry point
├── app/
│   ├── App.tsx           # app shell: the login page until a user is picked, then the page for the URL
│   ├── router.ts         # small router (no library): useLocation, navigate, linkTo
│   └── i18n.ts           # the language: t(), setLanguage(), dateLocale()
├── pages/                # one file per page, JSX only (HomePage, BbmPage, BbmReportPage, LoginPage, NotFoundPage)
├── controllers/          # one controller per page: its data, state, actions and backend calls
│   └── api.ts            #   the shared helpers for calling the backend (request, useApi, errorMessage, ...)
├── layouts/AppLayout.tsx # the frame of every signed-in page: navbar, language switch, current user
├── components/
│   ├── blue/             # BLUE3 components (BlueButton, BlueTable, BlueModal, BlueToast, ...)
│   └── *.tsx             # app components built on them (CommentThread, PhotoViewer, FileViewer, StatusBar, ...)
├── locales/en/, id/      # every text, one file per area (common, home, login, bbmList, report, components)
├── styles/               # all CSS, in the same folders as the code (styles/pages/BbmPage.css for pages/BbmPage.tsx)
├── types/                # shared types
└── utils/                # display helpers (format.ts: rupiah, numbers, dates, months; status labels; field names)
```

---

## Conventions

- **A page is three files:** `src/pages/<Name>Page.tsx` (JSX only), `src/controllers/<Name>Controller.ts` (its logic
  and backend calls, through `request()` from `api.ts`) and `src/styles/pages/<Name>Page.css`. No barrel `index.ts`
  files; import each file directly.
- **A new page** is one case in `routeOf()` and in `Page` in [App.tsx](src/app/App.tsx); a new navbar link is one
  entry in `navItems()` there.
- **BLUE3:** use the `Blue*` components and the `--blue-*` CSS tokens, not raw colours or plain HTML controls.
- **Formats** ([format.ts](src/utils/format.ts)): amounts `Rp 1.234.567` and numbers in Indonesian style, dates
  `DD-MM-YYYY`, in both languages.

---

## Languages

Indonesian is the default; the **ID | EN** switch (navbar and login page) is remembered in the browser.

- Every text lives in `src/locales/<language>/<area>.ts` and is read with `t()` from `src/app/i18n.ts`:
  `t("home:attention.start")`, or `t("reports", { count })` for plurals (`key_one` / `key_other`).
- Add a new text to the English file first: its keys are the ones `t()` accepts, so a mistyped key doesn't build.
  Then add it to the Indonesian file, which must have the same keys.
- Technical words stay English in both languages: Reimbursement, OCR, BBM, Reviewer, Grand total, Proceed, Excel,
  PDF. In Indonesian, reviewing is "review" (*perlu direview*, *Mulai review*), never *tinjau*.
- The API's error messages are English. In Indonesian the website shows its own text for the error code
  (`errors.codes` in `locales/id/common.ts`). The Excel export stays English (the backend makes it).

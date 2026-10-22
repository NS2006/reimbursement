import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import enBbmList from "../locales/en/bbmList";
import enCommon from "../locales/en/common";
import enComponents from "../locales/en/components";
import enHome from "../locales/en/home";
import enLogin from "../locales/en/login";
import enReport from "../locales/en/report";
import idBbmList from "../locales/id/bbmList";
import idCommon from "../locales/id/common";
import idComponents from "../locales/id/components";
import idHome from "../locales/id/home";
import idLogin from "../locales/id/login";
import idReport from "../locales/id/report";

// The website in English or Indonesian (i18next). The texts are in locales/<language>/<namespace>.ts, one namespace
// per area; t("bbmList:search.label") reads one, t("reviewStatus.approved.label") one of common (the default).
// Technical words (Reimbursement, OCR, BBM, Reviewer, Excel, PDF) stay English in both. Amounts and numbers are
// Indonesian style and dates DD-MM-YYYY in both languages; month and day names follow the language.
//
// t can be called anywhere while rendering (components, controllers, utils): switching the language renders the
// whole app again (App remounts the page, so memoised texts are made again too).

export const LANGUAGES = ["id", "en"] as const;
export type Language = (typeof LANGUAGES)[number];

/** New users see the website in Indonesian; the switch in the navbar is remembered in the browser. */
const DEFAULT_LANGUAGE: Language = "id";
const STORAGE_KEY = "reimbursement.language";

export const resources = {
  en: { common: enCommon, home: enHome, login: enLogin, bbmList: enBbmList, report: enReport, components: enComponents },
  id: { common: idCommon, home: idHome, login: idLogin, bbmList: idBbmList, report: idReport, components: idComponents },
};

function isLanguage(value: unknown): value is Language {
  return LANGUAGES.includes(value as Language);
}

function savedLanguage(): Language {
  try {
    const saved = window.localStorage.getItem(STORAGE_KEY);
    return isLanguage(saved) ? saved : DEFAULT_LANGUAGE;
  } catch {
    return DEFAULT_LANGUAGE; // storage blocked: the default
  }
}

void i18n.use(initReactI18next).init({
  resources,
  lng: savedLanguage(),
  fallbackLng: "en",
  ns: Object.keys(resources.en),
  defaultNS: "common",
  interpolation: { escapeValue: false }, // React escapes what it renders
  initAsync: false, // the texts are bundled: ready before the first render
});

document.documentElement.lang = i18n.language;
i18n.on("languageChanged", (lng) => {
  document.documentElement.lang = lng;
});

/** A text in the current language, e.g. t("home:attention.start") or t("reports", { count: 3 }). */
export const t = i18n.t.bind(i18n);

/** The language the website is shown in. */
export function language(): Language {
  return isLanguage(i18n.language) ? i18n.language : DEFAULT_LANGUAGE;
}

export function setLanguage(next: Language) {
  try {
    window.localStorage.setItem(STORAGE_KEY, next);
  } catch {
    // Not remembered (storage blocked): it still applies until the page is reloaded.
  }
  void i18n.changeLanguage(next);
}

/** The locale of month and day names ("Oktober 2026", "Kamis"); the digits stay DD-MM-YYYY. */
export function dateLocale(): string {
  return language() === "id" ? "id-ID" : "en-GB";
}

export default i18n;

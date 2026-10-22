import type { resources } from "../app/i18n";

// The keys t() accepts are the English texts' (locales/en): a mistyped or missing key does not build.
declare module "i18next" {
  interface CustomTypeOptions {
    defaultNS: "common";
    resources: (typeof resources)["en"];
  }
}

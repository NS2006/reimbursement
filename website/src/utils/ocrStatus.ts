import { t } from "../app/i18n";
import type { BlueAlertVariant, BlueBadgeVariant } from "../components/blue/types";
import type { OcrStatus } from "../types/reimbursement";

/** How each OCR status is shown, and what it means for the reviewer (hint: the short version). */
export const OCR_STATUSES: Record<
  OcrStatus,
  { label: string; badge: BlueBadgeVariant; alert: BlueAlertVariant; hint: string; meaning: string }
> = {
  needs_review: ocrStatus("needs_review", "error", "warning"),
  failed: ocrStatus("failed", "warning", "warning"),
  processing: ocrStatus("processing", "default", "info"),
  proceed: ocrStatus("proceed", "info", "info"),
  matched: ocrStatus("matched", "success", "success"),
};

/** The texts are read in the current language each time (getters). */
function ocrStatus(status: OcrStatus, badge: BlueBadgeVariant, alert: BlueAlertVariant) {
  return {
    badge,
    alert,
    get label() {
      return t(`ocrStatus.${status}.label`);
    },
    get hint() {
      return t(`ocrStatus.${status}.hint`);
    },
    get meaning() {
      return t(`ocrStatus.${status}.meaning`);
    },
  };
}

import { BlueBadge } from "./blue/Badge";
import type { OcrStatus } from "../types/reimbursement";
import { OCR_STATUSES } from "../utils/ocrStatus";

export function OcrStatusBadge({ status }: { status: OcrStatus }) {
  const { label, badge } = OCR_STATUSES[status];
  return (
    <BlueBadge variant={badge} dot>
      {label}
    </BlueBadge>
  );
}

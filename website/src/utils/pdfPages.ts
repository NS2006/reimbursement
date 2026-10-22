import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import { t } from "../app/i18n";

// Draws the pages of a PDF file as pictures with pdf.js (pdfjs-dist), so a PDF is looked at in the same viewer as
// a photo (components/PhotoViewer.tsx). pdf.js itself is loaded only when a PDF is opened.

/** Each page is drawn this many pixels on its longest side: sharp enough to zoom in on a receipt. */
const LONGEST_SIDE = 2400;
/** A small page (in PDF points) is not drawn bigger than this many times its size. */
const MAX_SCALE = 4;
/** A longer PDF shows its first pages only; the whole file opens in a new tab. */
export const MAX_PAGES = 30;

export interface PdfPages {
  /** Pages in the file. */
  count: number;
  /** Pages drawn (at most MAX_PAGES). */
  drawn: number;
}

/**
 * Draw the pages of a PDF one after the other; onPage gets each page as an image (a blob) as soon as it is drawn.
 * Stops (with an AbortError) when the signal is aborted.
 */
export async function drawPdfPages(
  data: ArrayBuffer,
  signal: AbortSignal,
  onPage: (page: Blob, number: number, count: number) => void,
): Promise<PdfPages> {
  const pdfjs = await import("pdfjs-dist");
  pdfjs.GlobalWorkerOptions.workerSrc = workerUrl;
  // Only the pages are drawn on a canvas: the PDF's own scripts never run, and XFA forms are not built.
  // (pdf.js 6 has no eval-based fonts any more, the cause of CVE-2024-4367.)
  const task = pdfjs.getDocument({ data, enableXfa: false });
  const stop = () => void task.destroy();
  signal.addEventListener("abort", stop, { once: true });
  try {
    const pdf = await task.promise;
    const drawn = Math.min(pdf.numPages, MAX_PAGES);
    for (let number = 1; number <= drawn; number += 1) {
      signal.throwIfAborted();
      const page = await pdf.getPage(number);
      const size = page.getViewport({ scale: 1 });
      const viewport = page.getViewport({
        scale: Math.min(MAX_SCALE, LONGEST_SIDE / Math.max(size.width, size.height)),
      });
      const canvas = document.createElement("canvas");
      canvas.width = Math.floor(viewport.width);
      canvas.height = Math.floor(viewport.height);
      const context = canvas.getContext("2d");
      if (!context) throw new Error(t("components:fileViewer.cannotDrawPdf"));
      context.fillStyle = "#ffffff"; // a page without a background is white, not transparent
      context.fillRect(0, 0, canvas.width, canvas.height);
      await page.render({ canvas, canvasContext: context, viewport }).promise;
      page.cleanup();
      onPage(await canvasBlob(canvas), number, pdf.numPages);
    }
    return { count: pdf.numPages, drawn };
  } finally {
    signal.removeEventListener("abort", stop);
    void task.destroy();
  }
}

function canvasBlob(canvas: HTMLCanvasElement): Promise<Blob> {
  return new Promise((resolve, reject) =>
    canvas.toBlob(
      (blob) => (blob ? resolve(blob) : reject(new Error(t("components:fileViewer.cannotDrawPdf")))),
      "image/jpeg",
      0.92,
    ),
  );
}

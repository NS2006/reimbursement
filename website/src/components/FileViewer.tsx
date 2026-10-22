import { useEffect, useState } from "react";
import { BlueButton } from "./blue/Button";
import { BlueSpinner } from "./blue/Spinner";
import { PhotoViewer, type ViewerPhoto } from "./PhotoViewer";
import { t } from "../app/i18n";
import { MAX_PAGES, drawPdfPages } from "../utils/pdfPages";
import "../styles/components/FileViewer.css";

export interface ViewerFile {
  id: number | string;
  /** File name, shown under the file. */
  name: string;
  /** Gets the file (rejects with an Error whose message can be shown). blob.type says what it is. */
  load: (signal: AbortSignal) => Promise<Blob>;
  /** Opens the file in a new tab (the browser shows images and PDFs itself). */
  openUrl: string;
}

interface FileViewerProps {
  files: ViewerFile[];
  /** What the files are, for screen readers, e.g. "Receipt". */
  label: string;
}

interface Problem {
  file: ViewerFile;
  message: string;
}

interface Loaded {
  /** Every page of every file so far: a photo is one page, a PDF one per page. */
  pages: ViewerPhoto[];
  problems: Problem[];
  /** PDF pages not drawn (beyond MAX_PAGES). */
  left: { file: ViewerFile; count: number }[];
  done: boolean;
}

const START: Loaded = { pages: [], problems: [], left: [], done: false };

// The receipt files of a report: photos and PDFs. Each is loaded, a PDF drawn page by page, and every page shown in
// the photo viewer (zoom, move, turn, expand; thumbnails pick a page). A file that can't be shown says why, with a
// link to it.
export function FileViewer({ files, label }: FileViewerProps) {
  const [loaded, setLoaded] = useState<Loaded>(START);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    const urls: string[] = [];
    setLoaded(START);

    function addPage(file: ViewerFile, blob: Blob, page?: { number: number; count: number }) {
      const src = URL.createObjectURL(blob);
      urls.push(src);
      const photo: ViewerPhoto = {
        id: page ? `${file.id}:${page.number}` : file.id,
        src,
        name: file.name,
        href: page ? `${file.openUrl}#page=${page.number}` : file.openUrl,
        downloadUrl: file.openUrl,
        page,
      };
      setLoaded((current) => ({ ...current, pages: [...current.pages, photo] }));
    }

    async function loadAll() {
      for (const file of files) {
        try {
          const blob = await file.load(controller.signal);
          if (blob.type.startsWith("image/")) {
            addPage(file, blob);
          } else if (blob.type === "application/pdf") {
            const { count, drawn } = await drawPdfPages(
              await blob.arrayBuffer(),
              controller.signal,
              (page, number, pageCount) => addPage(file, page, { number, count: pageCount }),
            );
            if (count > drawn) {
              setLoaded((current) => ({ ...current, left: [...current.left, { file, count: count - drawn }] }));
            }
          } else {
            throw new Error(t("components:fileViewer.notImageOrPdf"));
          }
        } catch (error) {
          if (controller.signal.aborted) return;
          const message = error instanceof Error && error.message ? error.message : t("components:fileViewer.failed");
          setLoaded((current) => ({ ...current, problems: [...current.problems, { file, message }] }));
        }
      }
      if (!controller.signal.aborted) setLoaded((current) => ({ ...current, done: true }));
    }

    void loadAll();
    return () => {
      controller.abort();
      urls.forEach((url) => URL.revokeObjectURL(url));
    };
  }, [files, attempt]);

  const { pages, problems, left, done } = loaded;

  if (pages.length === 0 && !done && problems.length === 0) {
    return (
      <div className="file-viewer__box">
        <BlueSpinner
          label={t(files.length > 1 ? "components:fileViewer.loadingFiles" : "components:fileViewer.loadingFile")}
        />
      </div>
    );
  }

  return (
    <div className="file-viewer">
      {pages.length > 0 ? <PhotoViewer photos={pages} label={label} /> : null}
      {!done && pages.length > 0 ? <p className="file-viewer__note">{t("components:fileViewer.drawing")}</p> : null}
      {left.map(({ file, count }) => (
        <p key={file.id} className="file-viewer__note">
          {t("components:fileViewer.firstPages", { name: file.name, max: MAX_PAGES })}{" "}
          <a href={file.openUrl} target="_blank" rel="noopener noreferrer">
            {t("components:fileViewer.openFile")}
          </a>{" "}
          {t("components:fileViewer.otherPages", { left: count })}
        </p>
      ))}
      {problems.map(({ file, message }) => (
        <div key={file.id} className="file-viewer__box file-viewer__box--problem" role="alert">
          <p className="file-viewer__title">{t("components:fileViewer.cannotShow", { name: file.name })}</p>
          <p className="file-viewer__message">{message}</p>
          <div className="file-viewer__actions">
            <BlueButton variant="secondary" size="sm" onClick={() => setAttempt((count) => count + 1)}>
              {t("actions.tryAgain")}
            </BlueButton>
          </div>
        </div>
      ))}
    </div>
  );
}

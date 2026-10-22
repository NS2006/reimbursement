import {
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
  type KeyboardEvent,
  type MouseEvent,
  type PointerEvent,
} from "react";
import { createPortal } from "react-dom";
import { BlueButton } from "./blue/Button";
import { t } from "../app/i18n";
import "../styles/components/PhotoViewer.css";

export interface ViewerPhoto {
  id: number | string;
  src: string;
  /** File name, shown under the photo and on its thumbnail. */
  name: string;
  /** "Open the original in a new tab" (src when not given). */
  href?: string;
  /** "Download": the file to save, under `name` (for a page of a PDF, the whole PDF). No button when not given. */
  downloadUrl?: string;
  /** A page of a PDF file. */
  page?: { number: number; count: number };
}

interface PhotoViewerProps {
  photos: ViewerPhoto[];
  /** What the photos are, for screen readers, e.g. "Receipt". */
  label: string;
}

/** "Page 2 of 3" for a page of a PDF, "2 of 3" for one of several photos; null for a single photo. */
function positionOf(photo: ViewerPhoto, photos: ViewerPhoto[]): string | null {
  if (photo.page && photo.page.count > 1) {
    return t("components:photoViewer.page", { number: photo.page.number, total: photo.page.count });
  }
  return photos.length > 1
    ? t("components:photoViewer.position", { number: photos.indexOf(photo) + 1, total: photos.length })
    : null;
}

/** What a screen reader says for the photo, e.g. "Receipt 2.jpeg" or "Receipt receipts.pdf, page 2 of 3". */
function titleOf(label: string, photo: ViewerPhoto): string {
  if (photo.page && photo.page.count > 1) {
    const { number, count } = photo.page;
    return t("components:photoViewer.titleWithPage", { label, name: photo.name, number, total: count });
  }
  return t("components:photoViewer.title", { label, name: photo.name });
}

/** Zoom and position of the photo. scale 1 = the whole photo fits the frame; turns = quarter turns clockwise. */
interface View {
  scale: number;
  x: number;
  y: number;
  turns: number;
}

interface Size {
  width: number;
  height: number;
}

const FIT: View = { scale: 1, x: 0, y: 0, turns: 0 };
const MAX_SCALE = 8;
const BUTTON_STEP = 1.5;
const DOUBLE_CLICK_SCALE = 2.5;
const KEY_PAN = 80;

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}

/** How big the photo is drawn at scale 1: as large as fits the frame, after turning it. */
function fittedSize(natural: Size, frame: Size, turns: number): Size {
  const turned = turns % 2 === 1;
  const across = turned ? natural.height : natural.width;
  const down = turned ? natural.width : natural.height;
  const factor = Math.min(frame.width / across, frame.height / down);
  return { width: natural.width * factor, height: natural.height * factor };
}

/** Keeps the zoom in range and the photo inside the frame (no panning into empty space). */
function clampView(view: View, natural: Size | null, frame: Size | null): View {
  const scale = clamp(view.scale, 1, MAX_SCALE);
  if (!natural || !frame) return { ...view, scale, x: 0, y: 0 };
  const fitted = fittedSize(natural, frame, view.turns);
  const turned = view.turns % 2 === 1;
  const shownWidth = (turned ? fitted.height : fitted.width) * scale;
  const shownHeight = (turned ? fitted.width : fitted.height) * scale;
  const maxX = Math.max(0, (shownWidth - frame.width) / 2);
  const maxY = Math.max(0, (shownHeight - frame.height) / 2);
  return { ...view, scale, x: clamp(view.x, -maxX, maxX), y: clamp(view.y, -maxY, maxY) };
}

// Receipt photos (or the pages of a PDF, see FileViewer.tsx), to read them closely without leaving the page:
// scroll (or pinch) on the photo to zoom where the pointer is, drag to move around, double-click to zoom in or
// back out, turn it when it was taken sideways, or expand it to the whole window. With several photos or pages,
// thumbnails pick one.
export function PhotoViewer({ photos, label }: PhotoViewerProps) {
  const [index, setIndex] = useState(0);
  const current = Math.min(index, photos.length - 1);
  const photo = photos[current];
  const hintId = useId();
  const pagerId = useId();
  // Set by "Previous" / "Next": the photo is drawn anew (see the key below), so the focus goes back to the button
  const stepped = useRef<Direction | null>(null);

  useEffect(() => {
    const direction = stepped.current;
    stepped.current = null;
    if (!direction) return;
    const pressed = document.getElementById(`${pagerId}-${direction}`);
    const other = document.getElementById(`${pagerId}-${direction === "next" ? "previous" : "next"}`);
    // At the first or the last photo the button pressed is disabled
    (pressed instanceof HTMLButtonElement && !pressed.disabled ? pressed : other)?.focus();
  }, [current, pagerId]);

  if (!photo) return null;

  function step(direction: Direction) {
    stepped.current = direction;
    setIndex(current + (direction === "next" ? 1 : -1));
  }

  return (
    <div className="photo-viewer-group">
      {/* key: another photo starts at its own zoom and position */}
      <SinglePhoto
        key={photo.src}
        photo={photo}
        label={label}
        hintId={hintId}
        position={positionOf(photo, photos)}
        pager={
          photos.length > 1
            ? {
                id: pagerId,
                unit: photos.every((candidate) => candidate.page) ? "page" : "photo",
                number: current + 1,
                count: photos.length,
                step,
              }
            : null
        }
      />
      {photos.length > 1 ? (
        <div
          className="photo-viewer__thumbnails"
          role="group"
          aria-label={t(
            photos.every((candidate) => candidate.page)
              ? "components:photoViewer.choosePage"
              : "components:photoViewer.choosePhoto",
          )}
        >
          {photos.map((candidate, candidateIndex) => (
            <button
              key={candidate.id}
              type="button"
              className="photo-viewer__thumbnail"
              aria-pressed={candidate === photo}
              aria-label={
                candidate.page
                  ? t("components:photoViewer.pageThumbnail", {
                      name: candidate.name,
                      number: candidate.page.number,
                      total: candidate.page.count,
                    })
                  : t("components:photoViewer.photoThumbnail", {
                      number: candidateIndex + 1,
                      total: photos.length,
                      name: candidate.name,
                    })
              }
              onClick={() => setIndex(candidateIndex)}
            >
              <img src={candidate.src} alt="" loading="lazy" />
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}

type Direction = "previous" | "next";

interface SinglePhotoProps {
  photo: ViewerPhoto;
  label: string;
  hintId: string;
  /** e.g. "1 of 3" when there are several photos, "Page 1 of 3" for a PDF page. */
  position: string | null;
  /** Several photos or pages: the buttons in the toolbar to go to the one before or after. */
  pager: { id: string; unit: "page" | "photo"; number: number; count: number; step: (direction: Direction) => void } | null;
}

function SinglePhoto({ photo, label, hintId, position, pager }: SinglePhotoProps) {
  const viewerRef = useRef<HTMLDivElement>(null);
  const frameRef = useRef<HTMLDivElement>(null);
  const expandButtonId = useId();
  const [natural, setNatural] = useState<Size | null>(null);
  const [frame, setFrame] = useState<Size | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "failed">("loading");
  const [view, setView] = useState<View>(FIT);
  const [dragging, setDragging] = useState(false);
  const [expanded, setExpanded] = useState(false);
  /** Keeps the viewer's place in the page while it is expanded, so the page behind does not jump. */
  const [placeholderHeight, setPlaceholderHeight] = useState(0);

  // The latest sizes, for the event handlers below (they are set up once, not on every render)
  const sizes = useRef({ natural, frame });
  useEffect(() => {
    sizes.current = { natural, frame };
  });
  const pointers = useRef(new Map<number, { x: number; y: number }>());

  const change = useCallback((update: (current: View) => View) => {
    setView((current) => clampView(update(current), sizes.current.natural, sizes.current.frame));
  }, []);

  /** Zoom by `factor`, keeping the photo point under `point` (relative to the frame's center) where it is. */
  const zoomAt = useCallback(
    (factor: number, point = { x: 0, y: 0 }) =>
      change((current) => {
        const scale = clamp(current.scale * factor, 1, MAX_SCALE);
        const ratio = scale / current.scale;
        return { ...current, scale, x: point.x - (point.x - current.x) * ratio, y: point.y - (point.y - current.y) * ratio };
      }),
    [change],
  );

  /** A screen position as a point relative to the frame's center. */
  const framePoint = useCallback((clientX: number, clientY: number) => {
    const rect = frameRef.current?.getBoundingClientRect();
    if (!rect) return { x: 0, y: 0 };
    return { x: clientX - rect.left - rect.width / 2, y: clientY - rect.top - rect.height / 2 };
  }, []);

  // The frame's size, kept up to date when the window or the layout changes
  useEffect(() => {
    const element = frameRef.current;
    if (!element) return;
    const observer = new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect;
      setFrame({ width, height });
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, [expanded]); // expanding draws the viewer elsewhere (see the end), with a new frame element

  // Scroll wheel and trackpad pinch zoom. Added by hand: React's onWheel cannot stop the page from scrolling.
  useEffect(() => {
    const element = frameRef.current;
    if (!element || status !== "ready") return;
    function onWheel(event: WheelEvent) {
      event.preventDefault();
      const pixels = event.deltaMode === WheelEvent.DOM_DELTA_LINE ? event.deltaY * 16 : event.deltaY;
      zoomAt(Math.exp(-pixels * 0.002), framePoint(event.clientX, event.clientY));
    }
    element.addEventListener("wheel", onWheel, { passive: false });
    return () => element.removeEventListener("wheel", onWheel);
  }, [status, expanded, zoomAt, framePoint]);

  // Expanded: Esc goes back. The focus moves into the photo, and back to the Expand button afterwards.
  // (An overlay in the page rather than the browser's full screen, which some browsers and policies block.)
  useEffect(() => {
    if (!expanded) return;
    frameRef.current?.focus();
    function onKey(event: globalThis.KeyboardEvent) {
      if (event.key === "Escape") setExpanded(false);
    }
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      document.getElementById(expandButtonId)?.focus();
    };
  }, [expanded, expandButtonId]);

  // The frame changes size when expanded and when the window is resized: keep the photo inside it
  useEffect(() => {
    setView((current) => clampView(current, natural, frame));
  }, [natural, frame]);

  function onPointerDown(event: PointerEvent<HTMLDivElement>) {
    if (status !== "ready" || (event.pointerType === "mouse" && event.button !== 0)) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    pointers.current.set(event.pointerId, { x: event.clientX, y: event.clientY });
    setDragging(true);
  }

  function onPointerMove(event: PointerEvent<HTMLDivElement>) {
    const before = pointers.current.get(event.pointerId);
    if (!before) return;
    const now = { x: event.clientX, y: event.clientY };
    const others = [...pointers.current].filter(([id]) => id !== event.pointerId).map(([, point]) => point);
    pointers.current.set(event.pointerId, now);

    if (others.length === 0) {
      change((current) => ({ ...current, x: current.x + now.x - before.x, y: current.y + now.y - before.y }));
    } else {
      // Two fingers: zoom by how much they moved apart, around the point between them
      const other = others[0];
      const distanceBefore = Math.hypot(before.x - other.x, before.y - other.y);
      const distanceNow = Math.hypot(now.x - other.x, now.y - other.y);
      if (distanceBefore > 0) {
        zoomAt(distanceNow / distanceBefore, framePoint((now.x + other.x) / 2, (now.y + other.y) / 2));
      }
    }
  }

  function onPointerEnd(event: PointerEvent<HTMLDivElement>) {
    pointers.current.delete(event.pointerId);
    if (pointers.current.size === 0) setDragging(false);
  }

  function onDoubleClick(event: MouseEvent<HTMLDivElement>) {
    if (status !== "ready") return;
    if (view.scale > 1) change(() => ({ ...FIT, turns: view.turns }));
    else zoomAt(DOUBLE_CLICK_SCALE, framePoint(event.clientX, event.clientY));
  }

  function toggleExpanded() {
    if (!expanded) setPlaceholderHeight(viewerRef.current?.offsetHeight ?? 0);
    setExpanded(!expanded);
  }

  function turn(by: number) {
    change((current) => ({ ...current, turns: (current.turns + by + 4) % 4, x: 0, y: 0 }));
  }

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    const actions: Record<string, () => void> = {
      "+": () => zoomAt(BUTTON_STEP),
      "=": () => zoomAt(BUTTON_STEP),
      "-": () => zoomAt(1 / BUTTON_STEP),
      "0": () => change((current) => ({ ...FIT, turns: current.turns })),
      r: () => turn(1),
      R: () => turn(-1),
      f: toggleExpanded,
      ArrowLeft: () => change((current) => ({ ...current, x: current.x + KEY_PAN })),
      ArrowRight: () => change((current) => ({ ...current, x: current.x - KEY_PAN })),
      ArrowUp: () => change((current) => ({ ...current, y: current.y + KEY_PAN })),
      ArrowDown: () => change((current) => ({ ...current, y: current.y - KEY_PAN })),
    };
    const action = actions[event.key];
    if (!action || event.ctrlKey || event.metaKey || event.altKey) return;
    event.preventDefault();
    action();
  }

  const fitted = natural && frame ? fittedSize(natural, frame, view.turns) : null;
  // The frame takes the photo's shape (as turned); expanded, it fills the window instead
  const frameShape =
    natural && !expanded
      ? view.turns % 2 === 1
        ? `${natural.height} / ${natural.width}`
        : `${natural.width} / ${natural.height}`
      : undefined;
  const zoomed = view.scale > 1.001;
  const frameClasses = [
    "photo-viewer__frame",
    zoomed ? "photo-viewer__frame--zoomed" : "",
    dragging ? "photo-viewer__frame--dragging" : "",
  ]
    .filter(Boolean)
    .join(" ");
  const pagerLabels =
    pager?.unit === "page"
      ? {
          group: t("components:photoViewer.pages"),
          previous: t("components:photoViewer.previousPage"),
          next: t("components:photoViewer.nextPage"),
        }
      : {
          group: t("components:photoViewer.photos"),
          previous: t("components:photoViewer.previousPhoto"),
          next: t("components:photoViewer.nextPhoto"),
        };

  const viewer = (
    <div
      ref={viewerRef}
      className={`photo-viewer ${expanded ? "photo-viewer--expanded" : ""}`.trim()}
      role={expanded ? "dialog" : undefined}
      aria-modal={expanded ? true : undefined}
      aria-label={expanded ? t("components:photoViewer.expandedTitle", { title: titleOf(label, photo) }) : undefined}
    >
      <div
        ref={frameRef}
        className={frameClasses}
        style={frameShape ? { aspectRatio: frameShape } : undefined}
        tabIndex={status === "ready" ? 0 : -1}
        role="group"
        aria-label={titleOf(label, photo)}
        aria-describedby={hintId}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerEnd}
        onPointerCancel={onPointerEnd}
        onDoubleClick={onDoubleClick}
        onKeyDown={onKeyDown}
      >
        {status === "failed" ? (
          <div className="photo-viewer__message" role="img" aria-label={titleOf(label, photo)}>
            <p className="photo-viewer__message-title">{t("components:photoViewer.failed")}</p>
            <a className="photo-viewer__message-link" href={photo.href ?? photo.src} target="_blank" rel="noopener noreferrer">
              {photo.href ?? photo.src}
            </a>
          </div>
        ) : (
          <>
            {status === "loading" ? (
              <p className="photo-viewer__message">{t("components:photoViewer.loading")}</p>
            ) : null}
            <img
              className="photo-viewer__image"
              src={photo.src}
              alt={titleOf(label, photo)}
              draggable={false}
              onLoad={(event) => {
                const { naturalWidth, naturalHeight } = event.currentTarget;
                setNatural({ width: naturalWidth, height: naturalHeight });
                setStatus("ready");
              }}
              onError={() => setStatus("failed")}
              style={
                fitted
                  ? {
                      width: fitted.width,
                      height: fitted.height,
                      transform: `translate(-50%, -50%) translate(${view.x}px, ${view.y}px) rotate(${view.turns * 90}deg) scale(${view.scale})`,
                    }
                  : { visibility: "hidden" }
              }
            />
          </>
        )}
      </div>

      <div className="photo-viewer__toolbar">
        <div className="photo-viewer__tools" role="toolbar" aria-label={t("components:photoViewer.controls")}>
          <BlueButton
            variant="ghost"
            size="sm"
            aria-label={t("components:photoViewer.zoomOut")}
            title={`${t("components:photoViewer.zoomOut")} (-)`}
            disabled={status !== "ready" || !zoomed}
            onClick={() => zoomAt(1 / BUTTON_STEP)}
          >
            <Icon name="minus" />
          </BlueButton>
          <BlueButton
            variant="ghost"
            size="sm"
            className="photo-viewer__zoom"
            aria-label={t("components:photoViewer.zoomLevel", { percent: Math.round(view.scale * 100) })}
            title={`${t("components:photoViewer.fit")} (0)`}
            disabled={status !== "ready" || !zoomed}
            onClick={() => change((current) => ({ ...FIT, turns: current.turns }))}
          >
            {Math.round(view.scale * 100)}%
          </BlueButton>
          <BlueButton
            variant="ghost"
            size="sm"
            aria-label={t("components:photoViewer.zoomIn")}
            title={`${t("components:photoViewer.zoomIn")} (+)`}
            disabled={status !== "ready" || view.scale >= MAX_SCALE}
            onClick={() => zoomAt(BUTTON_STEP)}
          >
            <Icon name="plus" />
          </BlueButton>
          <span className="photo-viewer__divider" aria-hidden="true" />
          <BlueButton
            variant="ghost"
            size="sm"
            aria-label={t("components:photoViewer.turnLeft")}
            title={`${t("components:photoViewer.turnLeft")} (Shift+R)`}
            disabled={status !== "ready"}
            onClick={() => turn(-1)}
          >
            <Icon name="turn-left" />
          </BlueButton>
          <BlueButton
            variant="ghost"
            size="sm"
            aria-label={t("components:photoViewer.turnRight")}
            title={`${t("components:photoViewer.turnRight")} (R)`}
            disabled={status !== "ready"}
            onClick={() => turn(1)}
          >
            <Icon name="turn-right" />
          </BlueButton>
        </div>
        {/* Not while expanded: another photo would close it (see the key in PhotoViewer) */}
        {pager && !expanded ? (
          <div className="photo-viewer__tools" role="group" aria-label={pagerLabels.group}>
            <BlueButton
              id={`${pager.id}-previous`}
              variant="ghost"
              size="sm"
              aria-label={pagerLabels.previous}
              title={pagerLabels.previous}
              disabled={pager.number === 1}
              onClick={() => pager.step("previous")}
            >
              <Icon name="previous" />
            </BlueButton>
            <span className="photo-viewer__position">
              {pager.number} / {pager.count}
            </span>
            <BlueButton
              id={`${pager.id}-next`}
              variant="ghost"
              size="sm"
              aria-label={pagerLabels.next}
              title={pagerLabels.next}
              disabled={pager.number === pager.count}
              onClick={() => pager.step("next")}
            >
              <Icon name="next" />
            </BlueButton>
          </div>
        ) : null}
        <div className="photo-viewer__tools">
          <BlueButton
            id={expandButtonId}
            variant="ghost"
            size="sm"
            aria-label={expanded ? t("components:photoViewer.shrink") : t("components:photoViewer.expand")}
            title={
              expanded ? `${t("components:photoViewer.shrink")} (Esc)` : `${t("components:photoViewer.expand")} (F)`
            }
            disabled={status === "failed"}
            onClick={toggleExpanded}
          >
            <Icon name={expanded ? "shrink" : "expand"} />
          </BlueButton>
          {photo.downloadUrl ? (
            <a
              className="photo-viewer__open"
              href={photo.downloadUrl}
              download={photo.name}
              aria-label={t("components:photoViewer.download", { name: photo.name })}
              title={t("components:photoViewer.download", { name: photo.name })}
            >
              <Icon name="download" />
            </a>
          ) : null}
          <a
            className="photo-viewer__open"
            href={photo.href ?? photo.src}
            target="_blank"
            rel="noopener noreferrer"
            aria-label={t("components:photoViewer.open")}
            title={t("components:photoViewer.open")}
          >
            <Icon name="external" />
          </a>
        </div>
      </div>

      <p id={hintId} className="photo-viewer__caption">
        <span className="photo-viewer__name">{photo.name}</span>
        {position ? <span> ({position})</span> : null}
        <span className="photo-viewer__hint photo-viewer__hint--mouse">
          {" "}
          · {t("components:photoViewer.mouseHint")}
        </span>
        <span className="photo-viewer__hint photo-viewer__hint--touch">
          {" "}
          · {t("components:photoViewer.touchHint")}
        </span>
      </p>
    </div>
  );

  if (!expanded) return viewer;
  // Expanded, it is drawn at the end of the page: inside the page layout, a sticky parent would keep it under
  // the navbar whatever its z-index.
  return (
    <>
      <div className="photo-viewer__placeholder" style={{ height: placeholderHeight }} aria-hidden="true" />
      {createPortal(viewer, document.body)}
    </>
  );
}

const ICON_PATHS = {
  plus: "M10 4v12M4 10h12",
  minus: "M4 10h12",
  "turn-left": "M4 4v5h5M4.6 9A6.5 6.5 0 1 1 6 14.5",
  "turn-right": "M16 4v5h-5M15.4 9A6.5 6.5 0 1 0 14 14.5",
  expand: "M3 8V3h5M12 3h5v5M17 12v5h-5M8 17H3v-5",
  shrink: "M8 3v5H3M17 8h-5V3M12 17v-5h5M3 12h5v5",
  external: "M11 3h6v6M17 3l-8 8M14 12v4a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h4",
  download: "M10 3v10M6 9l4 4 4-4M4 17h12",
  previous: "M12.5 4.5 7 10l5.5 5.5",
  next: "M7.5 4.5 13 10l-5.5 5.5",
} as const;

function Icon({ name }: { name: keyof typeof ICON_PATHS }) {
  return (
    <svg className="photo-viewer__icon" viewBox="0 0 20 20" aria-hidden="true">
      <path d={ICON_PATHS[name]} />
    </svg>
  );
}

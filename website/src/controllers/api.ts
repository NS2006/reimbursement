import { useCallback, useEffect, useRef, useState } from "react";
import { language, t } from "../app/i18n";
import enCommon from "../locales/en/common";

// General helpers for calling the Flask backend. In development Vite forwards /api to it (see vite.config.ts).
// The calls for one page live in that page's controller (e.g. LoginController.ts) and use request() below.

export class ApiError extends Error {
  readonly status: number;
  /** The backend's error code ("not_found", "decision_changed", …); null when it sent none. */
  readonly code: string | null;

  constructor(status: number, message: string, code: string | null = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

/** The address of a backend path, for a link (e.g. a file opened in a new tab). */
export function apiUrl(path: string): string {
  return `/api${path}`;
}

/** The response of a call that worked; an ApiError (with the backend's message) otherwise. */
async function send(path: string, init?: RequestInit): Promise<Response> {
  let response: Response;
  try {
    response = await fetch(apiUrl(path), init);
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ApiError(0, t("errors.unreachable"));
  }

  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null);
    throw new ApiError(
      response.status,
      errorBodyText(body, "message") ?? t("errors.http", { status: response.status }),
      errorBodyText(body, "error"),
    );
  }
  return response;
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await send(path, init);
  return (await response.json().catch(() => null)) as T;
}

/** A file the backend sends for download (e.g. an Excel export). */
export interface ApiFile {
  blob: Blob;
  /** The name the backend gave the file (Content-Disposition); null when it gave none. */
  name: string | null;
  headers: Headers;
}

export async function requestFile(path: string, init?: RequestInit): Promise<ApiFile> {
  const response = await send(path, init);
  let blob: Blob;
  try {
    blob = await response.blob();
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ApiError(0, t("errors.unreachable"));
  }
  return { blob, name: fileName(response.headers.get("Content-Disposition")), headers: response.headers };
}

/** filename*=UTF-8''… (any characters) wins over filename="…" (plain ASCII), as in the browsers. */
function fileName(disposition: string | null): string | null {
  if (!disposition) return null;
  const encoded = /filename\*\s*=\s*UTF-8''([^;]+)/i.exec(disposition);
  if (encoded) {
    try {
      return decodeURIComponent(encoded[1].trim());
    } catch {
      // Badly encoded: use the plain name below.
    }
  }
  const plain = /filename\s*=\s*(?:"([^"]*)"|([^;]+))/i.exec(disposition);
  return (plain?.[1] ?? plain?.[2])?.trim() || null;
}

/** The options for a call that sends JSON, e.g. request(path, jsonBody("POST", { description })). */
export function jsonBody(method: string, body: object): RequestInit {
  return { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
}

/** The backend's error answer: {"error": "not_found", "message": "No reimbursement with code RB-1."} */
function errorBodyText(body: unknown, field: "error" | "message"): string | null {
  if (typeof body === "object" && body !== null && field in body) {
    const value = (body as Record<string, unknown>)[field];
    if (typeof value === "string") return value;
  }
  return null;
}

type ErrorCode = keyof typeof enCommon.errors.codes;

function isErrorCode(code: string | null): code is ErrorCode {
  return code !== null && Object.hasOwn(enCommon.errors.codes, code);
}

/** What went wrong, for the reviewer. The backend's messages are English (the other systems read them too): in
 * English they are shown as they are (they have the details), in Indonesian by their error code. */
export function errorMessage(error: unknown): string {
  if (!(error instanceof ApiError)) return t("errors.generic");
  if (language() !== "en") {
    if (isErrorCode(error.code)) return t(`errors.codes.${error.code}`);
    if (error.code?.startsWith("invalid_")) return t("errors.invalidRequest");
  }
  return error.message;
}

// ---------------------------------------------------------------------------
// Loading data for a page
// ---------------------------------------------------------------------------

export type Loadable<T> =
  | { status: "loading" }
  | { status: "error"; message: string; notFound: boolean }
  | { status: "ready"; data: T };

/**
 * Load data when the component appears and again whenever `key` changes (e.g. the code of the report on the page).
 * A load that is no longer needed is cancelled. reload() loads again while the current data stays on screen
 * (refreshing is true meanwhile); update() changes the loaded data in place, e.g. after adding a comment,
 * without loading everything again. keepData: a new key also keeps the data on screen while it loads (e.g. the next
 * page of a list), instead of showing the loading state.
 */
export function useApi<T>(key: string, load: (signal: AbortSignal) => Promise<T>, { keepData = false } = {}) {
  const [state, setState] = useState<Loadable<T>>({ status: "loading" });
  const [refreshing, setRefreshing] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const loadRef = useRef(load);
  const loadedKey = useRef<string | null>(null);

  useEffect(() => {
    loadRef.current = load;
  });

  useEffect(() => {
    const controller = new AbortController();
    // Other data: show the loading state. The same data again (reload): keep it on screen until the new one is in.
    if (loadedKey.current === key || (keepData && loadedKey.current !== null)) {
      setRefreshing(true);
    } else {
      setState({ status: "loading" });
    }
    loadedKey.current = key;
    loadRef.current(controller.signal)
      .then((data) => setState({ status: "ready", data }))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setState({
          status: "error",
          message: errorMessage(error),
          notFound: error instanceof ApiError && error.status === 404,
        });
      })
      .finally(() => {
        if (!controller.signal.aborted) setRefreshing(false);
      });
    return () => controller.abort();
  }, [key, attempt, keepData]);

  const reload = useCallback(() => setAttempt((count) => count + 1), []);
  const update = useCallback(
    (change: (data: T) => T) => setState((current) => (current.status === "ready" ? { ...current, data: change(current.data) } : current)),
    [],
  );

  return { state, refreshing: refreshing && state.status === "ready", reload, update };
}

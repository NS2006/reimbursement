import { useMemo, useSyncExternalStore, type MouseEvent } from "react";

// A small router for the few pages of this app, so no routing library is needed: the page shown follows the
// browser URL, and links change the URL with history.pushState, so the page switches without reloading.
// Back and forward work as usual. The pages themselves are picked in app/App.tsx.

const listeners = new Set<() => void>();

function subscribe(listener: () => void) {
  listeners.add(listener);
  window.addEventListener("popstate", listener);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("popstate", listener);
  };
}

function currentUrl() {
  return window.location.pathname + window.location.search;
}

export interface AppLocation {
  /** e.g. "/bbm/EREP_10007", never with a trailing slash ("/" for the home page). */
  path: string;
  params: URLSearchParams;
}

/** The current page's path and query parameters; the component re-renders when they change. */
export function useLocation(): AppLocation {
  const url = useSyncExternalStore(subscribe, currentUrl);
  return useMemo(() => {
    const parsed = new URL(url, window.location.origin);
    return { path: parsed.pathname.replace(/\/+$/, "") || "/", params: parsed.searchParams };
  }, [url]);
}

/** Open another page of the app. replace: swap the current history entry instead of adding one (e.g. for a filter). */
export function navigate(to: string, { replace = false } = {}) {
  if (to === currentUrl()) return;
  if (replace) {
    window.history.replaceState(null, "", to);
  } else {
    window.history.pushState(null, "", to);
    window.scrollTo(0, 0);
  }
  listeners.forEach((listener) => listener());
}

/** Click handler for a link inside the app: a plain click opens the page without reloading, while
 *  Ctrl/Cmd/Shift-click, middle-click and target="_blank" keep their usual meaning (new tab or window). */
export function followLink(event: MouseEvent<HTMLAnchorElement>, to = event.currentTarget.getAttribute("href")) {
  const { target } = event.currentTarget;
  if (!to || event.defaultPrevented || event.button !== 0) return;
  if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || (target && target !== "_self")) return;
  event.preventDefault();
  navigate(to);
}

/** href and onClick of a link to a page of the app: <BlueLink {...linkTo("/bbm")}>BBM</BlueLink> */
export function linkTo(to: string) {
  return { href: to, onClick: (event: MouseEvent<HTMLAnchorElement>) => followLink(event, to) };
}

/** A URL with query parameters, leaving out the empty ones: withParams("/bbm", { q: "RB", status: "" }) is "/bbm?q=RB". */
export function withParams(path: string, params: Record<string, string | null | undefined>): string {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value) query.set(key, value);
  }
  const text = query.toString();
  return text ? `${path}?${text}` : path;
}
